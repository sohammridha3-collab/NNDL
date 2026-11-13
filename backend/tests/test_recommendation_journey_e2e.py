"""
End-to-End Regression Test Suite: Complete Live Recommendation Journey
Covers:
1. Full recommendation journey for Kolkata with résumé profile extraction.
2. Full recommendation journey for Delhi with strict preference filters (arrangement, level).
3. Deduplication across platform catalog and live authorized providers.
4. Resilient normalization for unknown/missing fields (salary, dates, requirements).
5. Provider failure resilience (429 Rate Limit, timeouts, network outages).
6. ML model inference failure fallback (truthful unranked preservation).
7. Saved jobs persistence and strict user data isolation (User A vs User B).
8. Live-provider smoke test (conditionally executed when credentials configured).
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Ensure OpenMP and HuggingFace single-threaded and offline on Windows
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.models import Company, Job, JobSkill, Resume, SavedJob, User
from app.schemas.schemas import (
    JobRecommendationItem,
    ResumeProfileSummaryRequest,
    SkillRecommendationRequest,
    SkillRecommendationResponse,
)
from app.services.job_providers.base import LiveJobListing, ProviderSearchResult
from app.services.job_providers.registry import registry
from app.services.recommendation_service import RecommendationService


class TestRecommendationJourneyE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Setup in-memory SQLite database for strict persistence and isolation testing
        cls.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

    def setUp(self):
        self.db = self.SessionLocal()
        # Seed test companies and users
        self.company1 = Company(name="Kolkata Tech Labs", location="Kolkata, WB")
        self.company2 = Company(name="Delhi Data Systems", location="New Delhi, DL")
        self.db.add_all([self.company1, self.company2])
        self.db.commit()

        # Seed User A and User B
        self.user_a = User(
            id="user_a_id",
            email="candidate_a@test.com",
            hashed_password="mock_hash_a",
            full_name="Candidate A (Kolkata)",
            role="candidate"
        )
        self.user_b = User(
            id="user_b_id",
            email="candidate_b@test.com",
            hashed_password="mock_hash_b",
            full_name="Candidate B (Delhi)",
            role="candidate"
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        # Clean all tables
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())
        self.db.commit()
        self.db.close()

    def test_1_kolkata_recommendation_journey_with_resume_summary(self):
        """
        Verify the 5-step journey for a Kolkata candidate:
        1. Parse profile summary from résumé text (canonical skills, non-overlapping tenure, detected titles).
        2. Execute live job search query targeting Kolkata.
        3. Verify live provider integration, matched skills, truthful freshness, and source URLs.
        """
        resume_text = (
            "Senior Software Engineer based in Kolkata, India. Email: candidate@kolkata.test\n"
            "Experience:\n"
            "• Senior Backend Engineer at Bengal Soft: 2021-06 to Present (Building scalable APIs with FastAPI and Docker)\n"
            "• Software Engineer at SaltLake Tech: 2019-01 to 2021-05 (Python microservices and PostgreSQL)\n"
            "Technical Skills: Python, FastAPI, Docker, PostgreSQL, REST APIs, Git, Redis."
        )

        # Step 1: Extract confirmed profile summary
        summary_req = ResumeProfileSummaryRequest(resume_text=resume_text)
        summary = RecommendationService.extract_profile_summary_from_resume(self.db, summary_req, current_user=self.user_a)

        self.assertFalse(summary.is_scanned)
        self.assertFalse(summary.recovery_needed)
        self.assertGreaterEqual(summary.total_experience_years, 4.0)
        self.assertIn("Python", [s.title() for s in summary.skills])
        self.assertIn("Docker", [s.title() for s in summary.skills])
        self.assertTrue(len(summary.detected_titles) > 0)

        # Mock live provider returning genuine Kolkata vacancies
        kolkata_provider_item = LiveJobListing(
            source_id="adzuna_kol_101",
            source_provider="adzuna",
            title="Senior Python / FastAPI Developer",
            company_name="CESC Digital",
            location="Kolkata, West Bengal",
            country="in",
            job_type="hybrid",
            description="We are hiring a Senior Python Developer with FastAPI, PostgreSQL, and Docker experience.",
            available_requirements=["Python", "FastAPI", "Docker", "PostgreSQL"],
            source_url="https://www.adzuna.in/details/101",
            application_url="https://www.adzuna.in/apply/101",
            posting_date="2026-11-10",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            source_label="Adzuna India"
        )
        non_matching_item = LiveJobListing(
            source_id="adzuna_beng_202",
            source_provider="adzuna",
            title="Backend Lead",
            company_name="Bangalore Systems",
            location="Bengaluru, Karnataka",
            country="in",
            job_type="on-site",
            description="Bengaluru onsite backend role.",
            available_requirements=["Java", "Spring"],
            source_url="https://www.adzuna.in/details/202",
            application_url="https://www.adzuna.in/apply/202",
            posting_date="2026-11-11",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            source_label="Adzuna India"
        )

        mock_search_res = ProviderSearchResult(
            provider="registry",
            status="success",
            message="Found vacancies",
            total=2,
            page=1,
            limit=12,
            items=[kolkata_provider_item, non_matching_item],
            cached=False
        )

        with patch.object(registry, "search_live_jobs", return_value=mock_search_res):
            rec_req = SkillRecommendationRequest(
                skills=["Python", "FastAPI", "Docker", "PostgreSQL"],
                preferred_titles=["Senior Software Engineer"],
                resume_text=resume_text,
                location="Kolkata",
                job_type="hybrid",
                include_external=True,
                limit=10,
                offset=0
            )

            res = RecommendationService.recommend_jobs_by_skills(self.db, rec_req, current_user=self.user_a)

            self.assertEqual(res.total, 1)
            item = res.items[0]
            self.assertEqual(item.id, "adzuna_kol_101")
            self.assertEqual(item.title, "Senior Python / FastAPI Developer")
            self.assertEqual(item.company_name, "CESC Digital")
            self.assertEqual(item.location, "Kolkata, West Bengal")
            self.assertEqual(item.job_type, "hybrid")
            self.assertEqual(item.source_url, "https://www.adzuna.in/details/101")
            self.assertEqual(item.application_url, "https://www.adzuna.in/apply/101")
            self.assertIn("Retrieved recently", item.freshness_label)
            self.assertFalse(item.is_cached)
            self.assertIsNotNone(item.retrieved_at)
            self.assertTrue(len(item.matched_skills) > 0)
            self.assertIn("Python", [s.title() for s in item.matched_skills])
            self.assertIn("score estimates résumé–job compatibility", item.disclaimer)

    def test_2_delhi_recommendation_journey_with_strict_filters(self):
        """
        Verify that Delhi searches strictly enforce user preferences:
        Filters: location='Delhi', job_type='hybrid', experience_level='Mid-Level'.
        Confirms zero silent relaxation: non-hybrid, non-Delhi, and mismatched levels are excluded.
        """
        # Seed curated database job in Delhi
        db_job_delhi_hybrid = Job(
            id="job_delhi_db_1",
            job_code="DEL-HYB-01",
            company_id=self.company2.id,
            title="Mid-Level Data Scientist",
            category="Data & AI",
            description="Data scientist role in Delhi working with Python, Machine Learning, and SQL.",
            requirements="Python, Machine Learning, SQL. 3-5 years experience.",
            location="New Delhi, DL",
            job_type="hybrid",
            experience_level="Mid-Level",
            status="active"
        )
        db_job_delhi_onsite = Job(
            id="job_delhi_db_2",
            job_code="DEL-ONS-02",
            company_id=self.company2.id,
            title="Onsite Data Engineer",
            category="Data & AI",
            description="Onsite data engineer in Delhi.",
            requirements="Python, SQL.",
            location="New Delhi, DL",
            job_type="on-site",
            experience_level="Mid-Level",
            status="active"
        )
        self.db.add_all([db_job_delhi_hybrid, db_job_delhi_onsite])
        self.db.commit()

        # Mock provider returning a Delhi hybrid job and a Delhi on-site job
        provider_delhi_hybrid = LiveJobListing(
            source_id="adzuna_del_hyb_1",
            source_provider="adzuna",
            title="Python ML Engineer",
            company_name="Delhi AI Labs",
            location="Connaught Place, Delhi",
            country="in",
            job_type="hybrid",
            experience_level="Mid-Level",
            description="Machine Learning Engineer with Python and PyTorch experience in Delhi hybrid setup.",
            available_requirements=["Python", "Machine Learning", "PyTorch"],
            source_url="https://www.adzuna.in/details/del1",
            application_url="https://www.adzuna.in/apply/del1",
            posting_date="2026-11-12",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            source_label="Adzuna India"
        )
        provider_delhi_onsite = LiveJobListing(
            source_id="adzuna_del_ons_2",
            source_provider="adzuna",
            title="Senior Python Developer",
            company_name="Delhi Enterprise",
            location="Noida, Delhi NCR",
            country="in",
            job_type="on-site",
            experience_level="Senior Level",
            description="Senior Python developer on-site.",
            available_requirements=["Python"],
            source_url="https://www.adzuna.in/details/del2",
            application_url="https://www.adzuna.in/apply/del2",
            posting_date="2026-11-12",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            source_label="Adzuna India"
        )

        mock_search_res = ProviderSearchResult(
            provider="registry",
            status="success",
            message="Found",
            total=2,
            page=1,
            limit=12,
            items=[provider_delhi_hybrid, provider_delhi_onsite],
            cached=True
        )

        with patch.object(registry, "search_live_jobs", return_value=mock_search_res):
            rec_req = SkillRecommendationRequest(
                skills=["Python", "Machine Learning", "PyTorch"],
                location="Delhi",
                job_type="hybrid",
                experience_level="Mid-Level",
                include_external=True
            )

            res = RecommendationService.recommend_jobs_by_skills(self.db, rec_req, current_user=self.user_b)

            # Both db_job_delhi_hybrid and provider_delhi_hybrid should pass.
            # db_job_delhi_onsite and provider_delhi_onsite must be excluded.
            self.assertEqual(res.total, 2)
            for item in res.items:
                self.assertEqual(item.job_type, "hybrid")
                self.assertIn("delhi", item.location.lower())

            # Verify cached flag from search result is propagated
            live_item = next(it for it in res.items if it.id == "adzuna_del_hyb_1")
            self.assertTrue(live_item.is_cached)
            self.assertIn("Cached", live_item.freshness_label)

    def test_3_deduplication_between_db_and_live_provider(self):
        """Verify identical listings across DB and provider feeds are cleanly deduplicated."""
        # Seed a DB job
        db_job = Job(
            id="job_common_01",
            job_code="INNO-01",
            company_id=self.company1.id,
            title="Full Stack Software Engineer",
            category="Information Technology",
            description="Developing web apps with React and FastAPI in Kolkata.",
            location="Kolkata, WB",
            job_type="remote",
            status="active"
        )
        self.db.add(db_job)
        self.db.commit()

        # Provider returns posting with exact same title and company name
        duplicate_provider_item = LiveJobListing(
            source_id="ext_duplicate_01",
            source_provider="adzuna",
            title="Full Stack Software Engineer",
            company_name=self.company1.name,
            location="Kolkata, West Bengal",
            country="in",
            job_type="remote",
            description="Developing web apps with React and FastAPI in Kolkata.",
            available_requirements=["React", "FastAPI"],
            source_url="https://www.adzuna.in/details/dup1",
            application_url="https://www.adzuna.in/apply/dup1",
            posting_date="2026-11-12",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            source_label="Adzuna India"
        )

        mock_search_res = ProviderSearchResult(
            provider="registry",
            status="success",
            message="Found",
            total=1,
            page=1,
            limit=12,
            items=[duplicate_provider_item],
            cached=False
        )

        with patch.object(registry, "search_live_jobs", return_value=mock_search_res):
            rec_req = SkillRecommendationRequest(
                skills=["React", "FastAPI"],
                location="Kolkata",
                include_external=True
            )
            res = RecommendationService.recommend_jobs_by_skills(self.db, rec_req, current_user=self.user_a)

            # Deduplication should preserve only 1 instance
            self.assertEqual(res.total, 1)

    def test_4_unknown_and_missing_fields_graceful_handling(self):
        """Verify provider listings with missing salary, requirements, dates do not cause errors."""
        sparse_item = LiveJobListing(
            source_id="adzuna_sparse_99",
            source_provider="adzuna",
            title="Junior Developer",
            company_name="Startup Studio",
            location="Kolkata, India",
            country="in",
            job_type="remote",
            min_salary=None,
            max_salary=None,
            salary_currency=None,
            posting_date=None,
            available_requirements=[],
            description="Short description for junior developer.",
            source_url="https://example.com/job99",
            application_url=None,
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            source_label="Adzuna India"
        )

        mock_search_res = ProviderSearchResult(
            provider="registry",
            status="success",
            message="Found",
            total=1,
            page=1,
            limit=12,
            items=[sparse_item]
        )

        with patch.object(registry, "search_live_jobs", return_value=mock_search_res):
            rec_req = SkillRecommendationRequest(
                skills=["Python"],
                location="Kolkata",
                include_external=True
            )
            res = RecommendationService.recommend_jobs_by_skills(self.db, rec_req, current_user=self.user_a)

            self.assertEqual(res.total, 1)
            item = res.items[0]
            self.assertIsNone(item.min_salary)
            self.assertIsNone(item.max_salary)
            self.assertIsNone(item.posted_date)
            # application_url falls back to source_url
            self.assertEqual(item.application_url, "https://example.com/job99")

    def test_5_provider_error_resilience_preserves_database_postings(self):
        """Verify provider network/rate-limit error does not crash the recommendation flow."""
        db_job = Job(
            id="job_fallback_01",
            job_code="FALLBACK-01",
            company_id=self.company1.id,
            title="Software Engineer",
            category="Information Technology",
            description="Database software engineer listing.",
            location="Kolkata, WB",
            job_type="remote",
            status="active"
        )
        self.db.add(db_job)
        self.db.commit()

        # Simulate provider returning error result (e.g. rate limited or connection failure)
        error_search_res = ProviderSearchResult(
            provider="registry",
            status="error",
            message="Rate limit 429 reached on Adzuna API",
            total=0,
            page=1,
            limit=12,
            items=[]
        )

        with patch.object(registry, "search_live_jobs", return_value=error_search_res):
            rec_req = SkillRecommendationRequest(
                skills=["Python"],
                location="Kolkata",
                include_external=True
            )
            res = RecommendationService.recommend_jobs_by_skills(self.db, rec_req, current_user=self.user_a)

            # Curated DB job is cleanly returned
            self.assertEqual(res.total, 1)
            self.assertEqual(res.items[0].id, "job_fallback_01")

    def test_6_model_inference_failure_preserves_unranked_vacancies(self):
        """Verify model failure preserves genuine vacancies as unranked rather than dropping them."""
        db_job = Job(
            id="job_unranked_01",
            job_code="UNRANKED-01",
            company_id=self.company1.id,
            title="Backend Architect",
            category="Information Technology",
            description="Comprehensive backend architect role responsible for designing distributed cloud microservices, database schemas, event queues, and fault-tolerant architecture.",
            location="Kolkata, WB",
            job_type="remote",
            status="active"
        )
        self.db.add(db_job)
        self.db.commit()

        with patch("app.services.recommendation_service.MLInferenceService.get_instance") as mock_ml_cls:
            mock_inst = MagicMock()
            mock_inst.encoder = MagicMock()
            mock_inst.vocabulary = {"python": ["python"], "architecture": ["architecture"]}
            # Force inference calculation to raise an unexpected runtime error
            mock_inst.predict_pair.side_effect = RuntimeError("Torch CUDA out of memory / thread lock")
            mock_inst.predict_proba.side_effect = RuntimeError("Torch CUDA out of memory / thread lock")
            mock_ml_cls.return_value = mock_inst

            rec_req = SkillRecommendationRequest(
                skills=["Architecture"],
                resume_text="Senior Architect with 10 years experience in distributed systems.",
                location="Kolkata",
                include_external=False
            )
            res = RecommendationService.recommend_jobs_by_skills(self.db, rec_req, current_user=self.user_a)

            self.assertEqual(res.total, 1)
            item = res.items[0]
            self.assertEqual(item.score_type, "unranked_inference_unavailable")
            self.assertIn("inference is currently initializing", item.relevance_explanation.lower())

    def test_7_saved_jobs_persistence_and_user_isolation(self):
        """
        Verify external job bookmarking persists in SQLite and ensures strict user isolation:
        User A bookmarks an external vacancy -> visible to User A only, not User B.
        """
        from app.api.jobs import save_external_job, list_my_saved_jobs

        payload = {
            "id": "adzuna_save_e2e_001",
            "job_code": "adzuna_save_e2e_001",
            "title": "Lead Cloud Architect",
            "company_name": "Tata Consultancy Services",
            "location": "Kolkata, West Bengal",
            "job_type": "hybrid",
            "experience_level": "Senior Level",
            "category": "Cloud & DevOps",
            "description": "Enterprise cloud architecture in Kolkata.",
            "requirements": "AWS, Kubernetes, Terraform.",
            "external_url": "https://www.adzuna.in/apply/e2e001"
        }

        # User A saves the external job
        res_a = save_external_job(payload=payload, current_user=self.user_a, db=self.db)
        self.assertTrue(res_a["saved"])
        self.assertEqual(res_a["job_id"], "adzuna_save_e2e_001")

        # Verify it exists in database
        saved_records = self.db.query(SavedJob).filter(SavedJob.job_id == "adzuna_save_e2e_001").all()
        self.assertEqual(len(saved_records), 1)
        self.assertEqual(saved_records[0].user_id, self.user_a.id)

        # Check User A's saved jobs list
        user_a_saved = list_my_saved_jobs(current_user=self.user_a, db=self.db)
        self.assertEqual(len(user_a_saved), 1)
        self.assertEqual(user_a_saved[0].id, "adzuna_save_e2e_001")
        self.assertEqual(user_a_saved[0].title, "Lead Cloud Architect")

        # Check User B's saved jobs list -> STRICT USER DATA ISOLATION
        user_b_saved = list_my_saved_jobs(current_user=self.user_b, db=self.db)
        self.assertEqual(len(user_b_saved), 0)

        # User A toggles / removes saved job
        res_a_remove = save_external_job(payload=payload, current_user=self.user_a, db=self.db)
        self.assertFalse(res_a_remove["saved"])
        user_a_saved_after = list_my_saved_jobs(current_user=self.user_a, db=self.db)
        self.assertEqual(len(user_a_saved_after), 0)

    def test_8_live_provider_smoke_if_configured(self):
        """
        Live smoke test against real Adzuna endpoint for Kolkata / Delhi vacancies.
        Runs ONLY when genuine credentials are in environment; skips gracefully otherwise.
        """
        app_id = os.getenv("ADZUNA_APP_ID")
        app_key = os.getenv("ADZUNA_APP_KEY")
        if not app_id or not app_key or app_id == "your_adzuna_app_id_here":
            self.skipTest("Adzuna API credentials not configured in environment. Skipping live network smoke test.")

        from app.services.job_providers.adzuna_provider import AdzunaJobProvider
        from app.services.job_providers.base import JobSearchQuery

        provider = AdzunaJobProvider(app_id=app_id, app_key=app_key, default_country="in")
        query = JobSearchQuery(
            keywords="Python Developer",
            location="Kolkata",
            country="in",
            page=1,
            limit=5
        )
        res = provider.search(query)
        self.assertEqual(res.status, "success")
        self.assertGreaterEqual(len(res.items), 0)
        if res.items:
            first = res.items[0]
            self.assertIsNotNone(first.source_id)
            self.assertIsNotNone(first.title)
            self.assertIsNotNone(first.source_url)


if __name__ == "__main__":
    unittest.main()

