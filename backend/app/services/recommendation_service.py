"""
Recommendation Service.
Integrates live authorized job providers (Adzuna India & Remotive Remote) with
résumé profile analysis, multi-query generation (zero PII leakage), strict preference
enforcement, qualification classification (required vs preferred), and PyTorch MatchNetwork inference.
"""
import html
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException
import numpy as np
from sqlalchemy.orm import Session

from app.ml.embeddings import EmbeddingEncoder
from app.ml.inference import MLInferenceService
from app.ml.preprocessing import (
    clean,
    calculate_skill_overlap,
    extract_skills,
    DEFAULT_SKILLS
)
from app.models.models import Job, Resume, SavedJob, User
from app.schemas.schemas import (
    EmploymentHistoryItem,
    JobRecommendationItem,
    ResumeProfileSummaryRequest,
    ResumeProfileSummaryResponse,
    SkillExtractionRequest,
    SkillExtractionResponse,
    SkillRecommendationRequest,
    SkillRecommendationResponse
)
from app.services.external_job_service import ExternalJobService
from app.services.job_providers.base import JobSearchQuery
from app.services.job_providers.registry import registry
from app.utils.file_extractor import (
    classify_job_qualifications,
    detect_role_titles,
    extract_resume_profile_summary,
    parse_employment_history
)

logger = logging.getLogger("inclusive_ats.recommendation_service")


class RecommendationService:

    @staticmethod
    def extract_profile_summary_from_resume(
        db: Session,
        request: ResumeProfileSummaryRequest,
        current_user: Optional[User] = None
    ) -> ResumeProfileSummaryResponse:
        """
        Parses an uploaded or stored resume into an editable profile summary:
        - Detects scanned/unreadable files and provides clear recovery guidance
        - Extracts skills, employment history, and possible role titles
        - Calculates non-overlapping tenure without double-counting overlapping jobs
        - Returns structured profile ready for candidate review and editing before searching.
        """
        raw_text = ""
        if request.resume_text and len(request.resume_text.strip()) >= 20:
            raw_text = request.resume_text.strip()
        elif request.resume_id:
            resume = db.query(Resume).filter(Resume.id == request.resume_id).first()
            if resume and current_user and current_user.role == "candidate" and resume.user_id != current_user.id:
                resume = None
            if not resume:
                raise HTTPException(status_code=404, detail="Resume record not found.")
            raw_text = resume.raw_text
        elif current_user:
            active_resume = db.query(Resume).filter(
                Resume.user_id == current_user.id,
                Resume.is_active == True
            ).first()
            if active_resume:
                raw_text = active_resume.raw_text

        if not raw_text or len(raw_text.strip()) < 30:
            return ResumeProfileSummaryResponse(
                readable=False,
                is_scanned=False,
                recovery_needed=True,
                recovery_message="No resume text available. Please upload a searchable PDF/DOCX or paste your résumé text.",
                raw_text="",
                skills=[],
                detected_titles=[],
                total_experience_years=0.0,
                employment_history=[],
            )

        summary_dict = extract_resume_profile_summary(text=raw_text)

        employment_items = [
            EmploymentHistoryItem(
                title=e["title"],
                company=e["company"],
                start_date=e.get("start_date"),
                end_date=e.get("end_date"),
                duration_months=e.get("duration_months", 0),
                description=e.get("description")
            )
            for e in summary_dict.get("employment_history", [])
        ]

        return ResumeProfileSummaryResponse(
            readable=summary_dict["readable"],
            is_scanned=summary_dict["is_scanned"],
            recovery_needed=summary_dict["recovery_needed"],
            recovery_message=summary_dict["recovery_message"],
            raw_text=summary_dict["raw_text"],
            summary=summary_dict.get("summary"),
            primary_role=summary_dict.get("primary_role"),
            detected_titles=summary_dict.get("detected_titles", []),
            skills=summary_dict.get("skills", []),
            total_experience_years=summary_dict.get("total_experience_years", 0.0),
            employment_history=employment_items,
            education=summary_dict.get("education", []),
            detected_location=summary_dict.get("detected_location"),
        )

    @staticmethod
    def extract_skills_from_input(
        db: Session,
        request: SkillExtractionRequest,
        current_user: Optional[User] = None
    ) -> SkillExtractionResponse:
        """
        Extracts recognized skills from an existing stored resume or direct text input.
        """
        inference_service = MLInferenceService.get_instance()
        vocab = inference_service.vocabulary

        target_text = ""
        source_label = "direct_text"

        input_text = request.resume_text or request.text
        if input_text and len(input_text.strip()) >= 15:
            target_text = input_text.strip()
            source_label = "pasted_text"
        elif request.resume_id:
            resume = db.query(Resume).filter(Resume.id == request.resume_id).first()
            if resume and current_user and current_user.role == "candidate" and resume.user_id != current_user.id:
                resume = None
            if not resume:
                raise HTTPException(status_code=404, detail="Resume record not found.")
            target_text = resume.raw_text
            source_label = f"resume:{resume.file_name}"
        elif current_user:
            active_resume = db.query(Resume).filter(
                Resume.user_id == current_user.id,
                Resume.is_active == True
            ).first()
            if active_resume:
                target_text = active_resume.raw_text
                source_label = f"active_resume:{active_resume.file_name}"

        if not target_text or len(target_text.strip()) < 15:
            raise HTTPException(
                status_code=400,
                detail="No resume text available for skill extraction. Please select a resume or paste text."
            )

        clean_text = clean(target_text, mask=True)
        skills = sorted(list(extract_skills(clean_text, vocab)))

        return SkillExtractionResponse(
            skills=skills,
            source=source_label,
            count=len(skills)
        )

    @classmethod
    def recommend_jobs_by_skills(
        cls,
        db: Session,
        req: SkillRecommendationRequest,
        current_user: Optional[User] = None
    ) -> SkillRecommendationResponse:
        """
        Complete live job recommendation pipeline:
        1. Resolves confirmed profile (skills, resume text, preferred titles).
        2. Builds multiple focused search queries (Zero PII Leakage: no name, email, or resume body sent).
        3. Retrieves genuine listings from connected live providers (Adzuna India / Remotive) + database.
        4. Strictly enforces user's explicit location, arrangement, and category preferences.
        5. Shortlists via semantic relevance and applies trained PyTorch neural model to complete descriptions.
        6. Keeps skills-only relevance separate from model compatibility.
        7. Returns evidence-based reasons, hiring disclaimer, or honest broadening suggestions if empty.
        """
        inference_service = MLInferenceService.get_instance()
        encoder = inference_service.encoder
        vocab = inference_service.vocabulary

        # -------------------------------------------------------------
        # 1. Resolve Profile & Resume Context
        # -------------------------------------------------------------
        resume_text = None
        if req.resume_text and len(req.resume_text.strip()) >= 20:
            resume_text = req.resume_text.strip()
        elif req.resume_id:
            res_obj = db.query(Resume).filter(Resume.id == req.resume_id).first()
            if res_obj and (not current_user or current_user.role != "candidate" or res_obj.user_id == current_user.id):
                resume_text = res_obj.raw_text

        has_resume_context = bool(resume_text and len(resume_text.strip()) >= 50)

        # Extract and normalize user skills
        user_skills_set: Set[str] = {s.strip().lower() for s in req.skills if s and s.strip()}
        if resume_text:
            extracted = extract_skills(clean(resume_text, mask=True), vocab)
            user_skills_set.update(extracted)

        user_skills: List[str] = sorted(list(user_skills_set))

        # Detect candidate role titles
        detected_roles = detect_role_titles(resume_text) if resume_text else []
        confirmed_titles = list(dict.fromkeys(req.preferred_titles + detected_roles))
        primary_title = confirmed_titles[0] if confirmed_titles else None

        # -------------------------------------------------------------
        # 2. Build Focused Search Queries (Strict Zero PII Leakage)
        # -------------------------------------------------------------
        focused_queries = cls._build_focused_queries(
            primary_role=primary_title,
            preferred_titles=req.preferred_titles,
            skills=user_skills,
            category=req.category
        )

        # -------------------------------------------------------------
        # 3. Retrieve Candidate Pool from Database & Live Providers
        # -------------------------------------------------------------
        candidate_pool: List[Dict[str, Any]] = []

        # 3A. Query Curated Database Jobs
        db_query = db.query(Job).filter(Job.status == "active")
        if req.category and req.category.strip():
            db_query = db_query.filter(Job.category.ilike(f"%{req.category.strip()}%"))
        if req.job_type and req.job_type.strip():
            db_query = db_query.filter(Job.job_type == req.job_type.strip().lower())
        if req.location and req.location.strip():
            db_query = db_query.filter(Job.location.ilike(f"%{req.location.strip()}%"))
        if req.experience_level and req.experience_level.strip():
            db_query = db_query.filter(Job.experience_level.ilike(f"%{req.experience_level.strip()}%"))
        if req.min_salary:
            db_query = db_query.filter(Job.max_salary >= req.min_salary)

        db_jobs = db_query.limit(40).all()
        for j in db_jobs:
            candidate_pool.append({
                "id": j.id,
                "job_code": j.job_code,
                "title": j.title,
                "company_name": j.company.name if j.company else "Verified Tech Partner",
                "location": j.location,
                "job_type": j.job_type,
                "experience_level": j.experience_level or "Mid-Level",
                "category": j.category or "Information Technology",
                "description": j.description,
                "requirements": j.requirements or "See job specifications.",
                "min_salary": j.min_salary,
                "max_salary": j.max_salary,
                "salary_currency": j.salary_currency or "INR",
                "posted_date": j.created_at.strftime("%b %d, %Y") if j.created_at else None,
                "source_type": "curated_dataset",
                "source_label": "Curated Dataset Listing",
                "external_url": None,
                "source_url": None,
                "application_url": None,
                "retrieved_at": j.created_at.strftime("%b %d, %Y") if j.created_at else None,
                "is_cached": False,
                "freshness_label": "Confirmed active (Curated Dataset)",
                "full_text": f"{j.title} {j.category or ''}\n{j.description}\n{j.requirements or ''}"
            })

        # 3B. Multi-Query Live Retrieval from Authorized Providers
        api_status = ExternalJobService.get_api_status()
        if req.include_external:
            for q_term in focused_queries:
                search_q = JobSearchQuery(
                    keywords=q_term,
                    location=req.location,
                    country=req.country or "in",
                    work_arrangement=req.job_type,
                    experience_level=req.experience_level,
                    category=req.category,
                    page=1,
                    limit=12
                )
                search_res = registry.search_live_jobs(search_q)
                if search_res.status == "success":
                    is_cached_query = getattr(search_res, "cached", False)
                    for item in search_res.items:
                        candidate_pool.append({
                            "id": item.source_id,
                            "job_code": item.source_id,
                            "title": item.title,
                            "company_name": item.company_name,
                            "location": item.location,
                            "job_type": item.job_type,
                            "experience_level": item.experience_level or "Mid-Level",
                            "category": item.category or "Information Technology",
                            "description": item.description,
                            "requirements": " ".join(item.available_requirements) if item.available_requirements else "See live posting.",
                            "min_salary": item.min_salary,
                            "max_salary": item.max_salary,
                            "salary_currency": item.salary_currency or "INR",
                            "posted_date": item.posting_date,
                            "source_type": "live_vacancy",
                            "source_label": item.source_label,
                            "external_url": item.application_url or item.source_url,
                            "source_url": item.source_url,
                            "application_url": item.application_url or item.source_url,
                            "retrieved_at": item.retrieval_timestamp,
                            "is_cached": is_cached_query,
                            "freshness_label": "Retrieved recently (Cached)" if is_cached_query else "Retrieved recently (Live Provider)",
                            "full_text": f"{item.title} {item.category or ''}\n{item.description}"
                        })

        # -------------------------------------------------------------
        # 4. Strict Filtering and Deduplication (Zero Preference Relaxation)
        # -------------------------------------------------------------
        deduped_pool: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        for c in candidate_pool:
            # Respect explicit work arrangement filter
            if req.job_type and req.job_type.lower() != c.get("job_type", "").lower():
                continue

            # Respect explicit location filter
            if req.location and req.location.strip():
                req_loc = req.location.strip().lower()
                cand_loc = (c.get("location") or "").lower()
                # Accept if exact location in text, or if remote is allowed and job is remote
                is_loc_match = (req_loc in cand_loc) or (c.get("job_type") == "remote" and req.job_type != "on-site")
                if not is_loc_match:
                    continue

            # Respect category filter
            if req.category and req.category.strip():
                req_cat = req.category.strip().lower()
                cand_cat = (c.get("category") or "").lower()
                if req_cat not in cand_cat:
                    continue

            sig = f"{c['title'].lower().strip()}::{c['company_name'].lower().strip()}"
            if sig not in seen_keys and c["title"]:
                seen_keys.add(sig)
                deduped_pool.append(c)

        # -------------------------------------------------------------
        # 5. Handle Empty Results (Explicit Diagnosis & Broadening Options)
        # -------------------------------------------------------------
        if not deduped_pool:
            empty_diag, suggestions = cls._build_broadening_suggestions(req, confirmed_titles)
            return SkillRecommendationResponse(
                total=0,
                page=(req.offset // req.limit) + 1 if req.limit else 1,
                limit=req.limit,
                active_skills=user_skills,
                has_resume_context=has_resume_context,
                api_status=api_status,
                items=[],
                empty_reason=empty_diag,
                broadening_suggestions=suggestions,
                queries_executed=focused_queries
            )

        # -------------------------------------------------------------
        # 6. Pre-scoring & Shortlisting
        # -------------------------------------------------------------
        saved_ids: Set[str] = set()
        if current_user:
            saved_records = db.query(SavedJob.job_id).filter(SavedJob.user_id == current_user.id).all()
            saved_ids = {r[0] for r in saved_records}

        # Encode candidate representation
        clean_resume_text = clean(resume_text, mask=True) if has_resume_context else None
        skills_text = f"Technical competencies: {', '.join(user_skills)}" if user_skills else "Software engineer technical qualifications"
        clean_skills_text = clean(skills_text, mask=True)
        skills_emb = encoder.encode([clean_skills_text])[0]

        scored_candidates: List[Dict[str, Any]] = []

        for candidate in deduped_pool:
            full_text = candidate["full_text"]
            clean_job = clean(full_text, mask=True)
            job_skills = extract_skills(clean_job, vocab)

            # Soft matching: does not require every candidate skill to appear
            matched_skills = sorted(list(user_skills_set & job_skills))
            missing_skills = sorted(list(job_skills - user_skills_set))
            overlap_ratio = float(len(matched_skills) / max(1, len(job_skills)))

            # Semantic similarity
            job_emb = encoder.encode([clean_job])[0]
            semantic_sim = float(np.dot(skills_emb, job_emb))
            semantic_sim = max(0.0, min(1.0, semantic_sim))

            initial_relevance = (semantic_sim * 0.6 + overlap_ratio * 0.4)

            # Classify job qualifications into required vs preferred vs general
            qual_breakdown = classify_job_qualifications(full_text)

            # Infer experience requirements from text
            exp_match = re.search(r'\b(\d+\+?\s*(?:to\s*\d+\+?)?\s*years?)\b', full_text, re.IGNORECASE)
            experience_req = exp_match.group(1) if exp_match else candidate.get("experience_level")

            scored_candidates.append({
                "candidate": candidate,
                "clean_job": clean_job,
                "job_skills": job_skills,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "overlap_ratio": overlap_ratio,
                "semantic_sim": semantic_sim,
                "initial_relevance": initial_relevance,
                "qual_breakdown": qual_breakdown,
                "experience_req": experience_req,
                "desc_len": len(candidate.get("description") or "")
            })

        # Shortlist top candidates (e.g. top 25)
        scored_candidates.sort(key=lambda x: x["initial_relevance"], reverse=True)
        shortlist = scored_candidates[:25]

        # -------------------------------------------------------------
        # 7. Model Compatibility Inference & Deep Reranking
        # -------------------------------------------------------------
        ranked_items: List[JobRecommendationItem] = []

        for item_data in shortlist:
            cand = item_data["candidate"]
            clean_job = item_data["clean_job"]
            matched = item_data["matched_skills"]
            missing = item_data["missing_skills"]
            semantic_sim = item_data["semantic_sim"]
            overlap_ratio = item_data["overlap_ratio"]
            relevance = item_data["initial_relevance"]
            desc_len = item_data["desc_len"]
            qual_breakdown = item_data["qual_breakdown"]
            experience_req = item_data["experience_req"]

            # Mode selection based on inputs
            if has_resume_context and desc_len >= 100:
                # Mode A: Full Neural Résumé–Job Compatibility (PyTorch MatchNetwork + 770-dim features)
                try:
                    pred = inference_service.predict_pair(
                        resume_text=clean_resume_text,
                        job_text=clean_job,
                        mask=True
                    )
                    score = pred["compatibility_score"]
                    score_type = "model_probability_percent"
                    score_label = "AI Résumé-Job Match Fit"
                    classification = pred["classification"]
                    semantic_similarity = pred["semantic_similarity"]
                    skill_coverage = pred["required_skill_coverage"]
                    relevance_explanation = (
                        f"Neural compatibility score: {score:.1f}% ({classification}). "
                        f"Matches {len(matched)} of {len(matched) + len(missing)} identified competencies with "
                        f"{semantic_similarity * 100:.1f}% semantic similarity to role specifications."
                    )
                except Exception as inf_err:
                    logger.warning(f"Neural inference fallback: {inf_err}")
                    score = round(relevance * 100, 1)
                    score_type = "unranked_inference_unavailable"
                    score_label = "Unranked (Inference Initializing)"
                    classification = "Preliminary Fit"
                    semantic_similarity = round(semantic_sim, 4)
                    skill_coverage = round(overlap_ratio, 4)
                    relevance_explanation = (
                        "Listing retrieved successfully. Neural compatibility inference is currently initializing; "
                        "results are ordered by preliminary keyword relevance."
                    )
            elif desc_len < 100:
                # Mode C: Incomplete / Brief Description (No fabricated score)
                score = round(relevance * 100, 1)
                score_type = "unranked_sparse_description"
                score_label = "Preliminary Listing (Brief Description)"
                classification = "Preliminary Match"
                semantic_similarity = round(semantic_sim, 4)
                skill_coverage = round(overlap_ratio, 4)
                relevance_explanation = (
                    f"Job description is brief ({desc_len} chars); compatibility estimated from role title and "
                    f"available skill keywords ({', '.join(matched[:3]) if matched else 'general match'})."
                )
            else:
                # Mode B: Skills-Only Relevance (Manual skill chips / brief input)
                score = round(relevance * 100, 1)
                score_type = "skills_only_relevance"
                score_label = "Skills-Only Relevance"
                classification = (
                    "High Skill Fit" if score >= 75
                    else ("Moderate Skill Fit" if score >= 50 else "Growth Opportunity")
                )
                semantic_similarity = round(semantic_sim, 4)
                skill_coverage = round(overlap_ratio, 4)
                relevance_explanation = (
                    f"Skills-only evaluation: matches {len(matched)} of {len(matched) + len(missing)} listed "
                    f"competencies ({', '.join(matched[:3]) if matched else 'general terms'}) with "
                    f"{semantic_similarity * 100:.1f}% semantic alignment."
                )

            is_saved = cand["id"] in saved_ids if cand.get("id") else False

            ranked_items.append(JobRecommendationItem(
                id=cand.get("id"),
                job_code=cand.get("job_code"),
                title=cand["title"],
                company_name=cand["company_name"],
                location=cand["location"],
                job_type=cand["job_type"],
                experience_level=cand.get("experience_level"),
                category=cand.get("category"),
                description=cand.get("description"),
                min_salary=cand.get("min_salary"),
                max_salary=cand.get("max_salary"),
                salary_currency=cand.get("salary_currency", "INR"),
                posted_date=cand.get("posted_date"),
                source_type=cand["source_type"],
                source_label=cand["source_label"],
                external_url=cand.get("external_url"),
                source_url=cand.get("source_url"),
                application_url=cand.get("application_url"),
                retrieved_at=cand.get("retrieved_at"),
                is_cached=cand.get("is_cached", False),
                freshness_label=cand.get("freshness_label", "Retrieved recently"),
                score=score,
                score_type=score_type,
                score_label=score_label,
                classification=classification,
                semantic_similarity=semantic_similarity,
                skill_coverage=skill_coverage,
                matched_skills=matched,
                missing_skills=missing,
                experience_requirements=experience_req,
                qualification_breakdown=qual_breakdown,
                relevance_explanation=relevance_explanation,
                disclaimer="This score estimates résumé–job compatibility according to the model’s training labels. It is not the probability of being hired.",
                is_saved=is_saved
            ))

        ranked_items.sort(key=lambda x: x.score, reverse=True)

        total_count = len(ranked_items)
        paginated = ranked_items[req.offset : req.offset + req.limit]
        current_page = (req.offset // req.limit) + 1 if req.limit else 1

        return SkillRecommendationResponse(
            total=total_count,
            page=current_page,
            limit=req.limit,
            active_skills=user_skills,
            has_resume_context=has_resume_context,
            api_status=api_status,
            items=paginated,
            empty_reason=None,
            broadening_suggestions=[],
            queries_executed=focused_queries
        )

    @staticmethod
    def _build_focused_queries(
        primary_role: Optional[str],
        preferred_titles: List[str],
        skills: List[str],
        category: Optional[str]
    ) -> List[str]:
        """
        Builds focused, sanitized queries sending ONLY technical terms.
        Candidate PII (name, email, phone, university) is NEVER sent.
        """
        queries: List[str] = []
        safe_skills = [re.sub(r'[^a-zA-Z0-9+#. ]', '', s).strip() for s in skills if s and len(s) > 1]
        top_skills = safe_skills[:6]

        # Query 1: Primary detected/preferred role + top 2 skills
        if primary_role:
            clean_role = re.sub(r'[^a-zA-Z0-9 ]', '', primary_role).strip()
            role_terms = f"{clean_role} {' '.join(top_skills[:2])}".strip()
            if role_terms:
                queries.append(role_terms)

        # Query 2: Alternate preferred titles
        for t in preferred_titles[:2]:
            clean_t = re.sub(r'[^a-zA-Z0-9 ]', '', t).strip()
            if clean_t and clean_t.lower() != (primary_role or "").lower():
                q_alt = f"{clean_t} {' '.join(top_skills[:2])}".strip()
                if q_alt and q_alt not in queries:
                    queries.append(q_alt)

        # Query 3: Skill cluster
        if len(top_skills) >= 2:
            skill_q = " ".join(top_skills[:3])
            if skill_q not in queries:
                queries.append(skill_q)

        # Fallback query
        if not queries:
            queries.append(category or "Software Engineer")

        return queries[:3]

    @staticmethod
    def _build_broadening_suggestions(
        req: SkillRecommendationRequest,
        detected_titles: List[str]
    ) -> Tuple[str, List[str]]:
        """
        Explains why no results matched and offers explicit options to broaden.
        Never silently relaxes user preferences.
        """
        filters_applied = []
        suggestions = []

        if req.location and req.location.strip():
            filters_applied.append(f"location '{req.location.strip()}'")
            suggestions.append(
                f"Broaden location: Consider enabling 'Remote' work or expanding to nearby tech hubs (e.g. Kolkata, Delhi NCR, Bengaluru)."
            )

        if req.job_type and req.job_type.strip() and req.job_type.lower() != "all":
            filters_applied.append(f"work arrangement '{req.job_type.strip()}'")
            suggestions.append(
                "Relax work arrangement: Select 'Any Arrangement' to view hybrid and remote opportunities."
            )

        if req.experience_level and req.experience_level.strip():
            filters_applied.append(f"seniority '{req.experience_level.strip()}'")
            suggestions.append(
                "Clear experience level: Remove the strict seniority filter to see openings with flexible requirements."
            )

        if req.preferred_titles:
            suggestions.append(
                f"Try related role titles: {', '.join(detected_titles[:3]) if detected_titles else 'Software Developer, Backend Engineer, or Tech Lead'}."
            )

        if not suggestions:
            suggestions.append("Add 2-3 additional technical skills to widen matching opportunities.")

        reason = (
            f"No vacancies currently match all your strict filters ({', '.join(filters_applied)})."
            if filters_applied
            else "No vacancies currently match the specified criteria."
        )

        return reason, suggestions

    @staticmethod
    def get_job_recommendations_for_user(
        db: Session,
        user: User,
        top_k: int = 10,
        category: Optional[str] = None,
        job_type: Optional[str] = None,
        location: Optional[str] = None,
        min_salary: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Legacy helper for dashboard compatibility."""
        req = SkillRecommendationRequest(
            category=category,
            job_type=job_type,
            location=location,
            min_salary=min_salary,
            limit=top_k,
            include_external=False
        )
        res = RecommendationService.recommend_jobs_by_skills(db, req, user)
        return [item.model_dump() for item in res.items]
