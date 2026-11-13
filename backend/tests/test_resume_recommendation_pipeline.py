"""
Test Suite: Résumé-Based Job Recommendation Pipeline
Covers:
1. Scanned / image-based PDF detection and actionable recovery advice.
2. Accurate non-overlapping employment tenure calculation (no double-counting concurrent roles).
3. Focused job query construction with zero PII leakage (no candidate name, email, phone, or raw text).
4. Qualification classification (required vs preferred vs general) and soft-matching.
5. Score type separation: neural model compatibility vs skills-only relevance vs brief description handling.
6. Evidence-based explanations and mandatory hiring disclaimer.
7. Strict preference preservation (no silent relaxation) and explicit broadening suggestions.
8. Inference failure graceful preservation of retrieved vacancies as unranked results.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure OpenMP and HuggingFace single-threaded and offline on Windows
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.file_extractor import (
    ScannedDocumentError,
    extract_resume_profile_summary,
    extract_resume_text,
    extract_text_from_pdf,
    merge_date_intervals,
    parse_employment_history,
    classify_job_qualifications,
    detect_role_titles
)
from app.schemas.schemas import (
    JobRecommendationItem,
    ResumeProfileSummaryRequest,
    SkillRecommendationRequest,
    SkillRecommendationResponse
)
from app.services.job_providers.base import ProviderSearchResult
from app.services.recommendation_service import RecommendationService
from app.ml.inference import MLInferenceService
from app.models.models import Job, Resume, User


def get_empty_provider_result():
    return ProviderSearchResult(
        provider="registry",
        status="success",
        message="No external vacancies",
        total=0,
        page=1,
        limit=12,
        items=[]
    )


def make_mock_db(jobs):
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = jobs
    mock_db.query.return_value = mock_query
    return mock_db


class TestResumeRecommendationPipeline(unittest.TestCase):

    def test_1_scanned_pdf_detection_and_recovery(self):
        """Verify scanned or unreadable documents trigger recovery mode with clear instructions."""
        # Simulated scanned PDF where extracted text is below 35 chars
        with patch("app.utils.file_extractor.PdfReader") as mock_pdf:
            mock_reader = MagicMock()
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "   "
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = " Page 2 "
            mock_reader.pages = [mock_page1, mock_page2]
            mock_pdf.return_value = mock_reader

            with self.assertRaises(ScannedDocumentError) as ctx:
                extract_resume_text(b"%PDF-1.4 dummy pdf bytes", "scan.pdf")
            self.assertIn("scanned image", str(ctx.exception).lower())
            self.assertIn("paste", ctx.exception.recovery_message.lower())

        # Test profile summary with scanned document error
        with patch(
            "app.utils.file_extractor.extract_resume_text",
            side_effect=ScannedDocumentError(
                message="Scanned PDF detected",
                recovery_message="Your document appears to be a scanned or image-based PDF. Please paste your résumé text directly into the text area below."
            )
        ):
            summary = extract_resume_profile_summary(file_bytes=b"dummy", file_name="resume.pdf")
            self.assertTrue(summary["is_scanned"])
            self.assertTrue(summary["recovery_needed"])
            self.assertIn("scanned or image-based", summary["recovery_message"].lower())

        # When plain text is provided, recovery should NOT be needed
        valid_text = (
            "Alex Mercer - Senior Software Engineer\n"
            "Email: alex@example.com Phone: 555-0199\n"
            "Experience:\n"
            "Software Engineer at Acme Corp (Jan 2020 - Dec 2022)\n"
            "Developed backend APIs using Python, FastAPI, Docker, and PostgreSQL.\n"
            "Skills: Python, FastAPI, Docker, SQL, Kubernetes, AWS, Machine Learning."
        )
        valid_summary = extract_resume_profile_summary(text=valid_text)
        self.assertFalse(valid_summary["is_scanned"])
        self.assertFalse(valid_summary["recovery_needed"])
        self.assertIn("python", valid_summary["skills"])
        self.assertIn("docker", valid_summary["skills"])

    def test_2_non_overlapping_tenure_calculation(self):
        """Verify overlapping concurrent employment periods are merged without double-counting."""
        # Role 1: Jan 2020 to Jan 2022 (24 months)
        # Role 2: Jun 2021 to Jun 2022 (12 months - overlaps Role 1 by 7 months)
        # Total merged timeline: Jan 2020 to Jun 2022 = 30 months = 2.50 years (NOT 36 months / 3.0 years)
        intervals = [
            (2020 * 12 + 1, 2022 * 12 + 1),  # Jan 2020 - Jan 2022
            (2021 * 12 + 6, 2022 * 12 + 6)   # Jun 2021 - Jun 2022
        ]
        merged_intervals, total_months = merge_date_intervals(intervals)
        self.assertEqual(len(merged_intervals), 1)
        self.assertEqual(total_months, 30)

        # Test via resume text parsing with concurrent overlapping positions
        resume_text_with_overlap = (
            "John Doe\n"
            "Full Stack Engineer at InnovateTech (Jan 2020 - Dec 2022)\n"
            "Concurrent Contractor at CloudCorp (Jun 2021 - Jun 2022)\n"
            "Skills: Python, React, PostgreSQL."
        )
        parsed = extract_resume_profile_summary(text=resume_text_with_overlap)
        # Total non-overlapping duration is Jan 2020 to Dec 2022 = 36 months = 3.0 years
        self.assertAlmostEqual(parsed["total_experience_years"], 3.0, delta=0.2)

    def test_3_focused_query_generation_zero_pii(self):
        """Verify only focused technical search terms are generated without candidate PII."""
        queries = RecommendationService._build_focused_queries(
            primary_role="Backend Engineer",
            preferred_titles=["Backend Engineer", "Software Developer"],
            skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS"],
            category="Software"
        )

        self.assertGreater(len(queries), 0)
        joined_queries = " ".join(queries)
        self.assertTrue(any("Backend Engineer" in q or "Python" in q for q in queries))

        # STRICT PII CHECK: No candidate personal identifying details in search queries
        candidate_pii = ["Alex Mercer", "alex.mercer@private.io", "9876543210", "Park Street", "700016"]
        for pii in candidate_pii:
            self.assertNotIn(pii, joined_queries)

    def test_4_qualification_classification_and_soft_matching(self):
        """Verify requirements are cleanly classified into required vs preferred without strict elimination."""
        requirements_block = (
            "Must have 3+ years experience with Python and FastAPI.\n"
            "Required: Solid understanding of relational databases and SQL.\n"
            "Nice to have: Experience with Kubernetes or Docker.\n"
            "Preferred: Familiarity with AWS and serverless architectures.\n"
            "Bachelor's degree in Computer Science or equivalent practical experience."
        )

        classified = classify_job_qualifications(requirements_block)
        self.assertIn("required", classified)
        self.assertIn("preferred", classified)

        req_joined = " ".join(classified["required"]).lower()
        pref_joined = " ".join(classified["preferred"]).lower()

        self.assertTrue("python" in req_joined or "fastapi" in req_joined or "sql" in req_joined)
        self.assertTrue("kubernetes" in pref_joined or "aws" in pref_joined)

    def test_5_score_type_separation(self):
        """Verify separation between neural match compatibility, skills-only relevance, and sparse descriptions."""
        # Job with sparse description (< 100 chars)
        sparse_job = Job(
            id="job_sparse_1",
            job_code="SPARSE01",
            title="Junior Coder",
            location="Remote",
            job_type="remote",
            description="We need a programmer.",  # Sparse (< 100 chars)
            requirements="Python",
            category="Software",
            status="active"
        )

        # Job with full rich description (>= 100 chars)
        rich_job = Job(
            id="job_rich_1",
            job_code="RICH01",
            title="Senior Python Developer",
            location="Kolkata",
            job_type="hybrid",
            description=(
                "We are seeking an experienced Senior Python Developer to architect scalable backend microservices, "
                "develop RESTful and GraphQL APIs using FastAPI and Flask, optimize PostgreSQL queries, and lead "
                "containerized deployments across Kubernetes and AWS."
            ),
            requirements="5+ years Python, FastAPI, Docker, PostgreSQL, AWS required.",
            category="Software",
            status="active"
        )

        mock_db = make_mock_db([sparse_job, rich_job])

        # Case A: Request without resume text (Skills-Only)
        skills_req = SkillRecommendationRequest(
            skills=["Python", "FastAPI", "Docker", "PostgreSQL"],
            include_external=False
        )

        with patch("app.services.recommendation_service.registry.search_live_jobs", return_value=get_empty_provider_result()):
            res_skills = RecommendationService.recommend_jobs_by_skills(
                db=mock_db,
                req=skills_req,
                current_user=None
            )

        self.assertEqual(res_skills.total, 2)
        score_types = {item.id: item.score_type for item in res_skills.items}
        # Sparse description job must be unranked_sparse_description
        self.assertEqual(score_types["job_sparse_1"], "unranked_sparse_description")
        # Rich description job in skills-only mode must be skills_only_relevance
        self.assertEqual(score_types["job_rich_1"], "skills_only_relevance")

    def test_6_evidence_based_explanation_and_disclaimer(self):
        """Verify each recommendation contains evidence-based reasons and the mandatory hiring disclaimer."""
        sample_job = Job(
            id="job_ev_1",
            job_code="EV01",
            title="MLOps Engineer",
            location="Bengaluru",
            job_type="on-site",
            description=(
                "NeuroTech is hiring an MLOps Engineer to productionize machine learning models, build CI/CD pipelines "
                "with Docker and GitHub Actions, and monitor model drift in AWS cloud environments."
            ),
            requirements="Experience with Python, Docker, PyTorch, and AWS.",
            category="Software",
            status="active"
        )
        mock_db = make_mock_db([sample_job])

        req = SkillRecommendationRequest(
            skills=["Python", "Docker", "AWS"],
            include_external=False
        )

        with patch("app.services.recommendation_service.registry.search_live_jobs", return_value=get_empty_provider_result()):
            res = RecommendationService.recommend_jobs_by_skills(
                db=mock_db,
                req=req,
                current_user=None
            )

        self.assertEqual(len(res.items), 1)
        item = res.items[0]
        # Evidence explanation
        self.assertTrue(len(item.relevance_explanation) > 10)
        # Skills are normalized
        self.assertIn("python", [s.lower() for s in item.matched_skills])
        # Mandatory Hiring Disclaimer
        expected_disclaimer = "This score estimates résumé–job compatibility according to the model’s training labels. It is not the probability of being hired."
        self.assertEqual(item.disclaimer, expected_disclaimer)

    def test_7_no_silent_relaxation_and_broadening_suggestions(self):
        """Verify that when 0 listings match, preferences are NOT silently relaxed, and broadening options are returned."""
        mock_db = make_mock_db([])

        # User specifically asks for Kolkata and on-site with non-matching title
        strict_req = SkillRecommendationRequest(
            skills=["Kubernetes"],
            location="NonExistentCity999",
            job_type="on-site",
            include_external=False
        )

        with patch("app.services.recommendation_service.registry.search_live_jobs", return_value=get_empty_provider_result()):
            res = RecommendationService.recommend_jobs_by_skills(
                db=mock_db,
                req=strict_req,
                current_user=None
            )

        self.assertEqual(res.total, 0)
        self.assertEqual(len(res.items), 0)
        self.assertIsNotNone(res.empty_reason)
        self.assertIn("NonExistentCity999", res.empty_reason)
        # Broadening suggestions must be actionable
        self.assertGreater(len(res.broadening_suggestions), 0)
        suggestions_joined = " ".join(res.broadening_suggestions)
        self.assertTrue("location" in suggestions_joined.lower() or "remote" in suggestions_joined.lower())

    def test_8_inference_failure_preserves_unranked_listings(self):
        """Verify that an ML inference failure preserves genuine vacancies as unranked results."""
        job = Job(
            id="job_inf_1",
            job_code="INF01",
            title="Senior Platform Engineer",
            location="Delhi",
            job_type="hybrid",
            description="Developing scalable cloud infrastructure with Kubernetes, Go, and Terraform across global regions with high availability.",
            requirements="Kubernetes, Terraform, Go.",
            category="Software",
            status="active"
        )
        mock_db = make_mock_db([job])

        req = SkillRecommendationRequest(
            skills=["Kubernetes", "Go"],
            resume_text="Senior Platform Engineer with 8 years building Kubernetes cloud clusters with Python and Go.",
            include_external=False
        )

        # Mock MLInferenceService.predict_pair to simulate runtime failure
        with patch.object(MLInferenceService, "predict_pair", side_effect=RuntimeError("GPU OOM / Internal Failure")):
            with patch("app.services.recommendation_service.registry.search_live_jobs", return_value=get_empty_provider_result()):
                res = RecommendationService.recommend_jobs_by_skills(
                    db=mock_db,
                    req=req,
                    current_user=None
                )

        # Listing must be preserved, not dropped!
        self.assertEqual(res.total, 1)
        self.assertEqual(len(res.items), 1)
        self.assertEqual(res.items[0].id, "job_inf_1")
        self.assertEqual(res.items[0].score_type, "unranked_inference_unavailable")
        self.assertIn("Neural compatibility inference", res.items[0].relevance_explanation)


if __name__ == "__main__":
    unittest.main()
