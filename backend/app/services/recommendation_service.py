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
    JobRecommendationItem,
    SkillExtractionRequest,
    SkillExtractionResponse,
    SkillRecommendationRequest,
    SkillRecommendationResponse
)
from app.services.external_job_service import ExternalJobService

logger = logging.getLogger("inclusive_ats.recommendation_service")


class RecommendationService:
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
            # Fall back to user's active resume
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

    @staticmethod
    def recommend_jobs_by_skills(
        db: Session,
        req: SkillRecommendationRequest,
        current_user: Optional[User] = None
    ) -> SkillRecommendationResponse:
        """
        Dual-source recommendation engine combining:
        1. Curated database postings.
        2. Authorized live vacancies (Adzuna Developer API or Remotive Open API).
        
        Evaluates relevance:
        - Mode A (Full Résumé Available): Runs real PyTorch MatchNetwork (770-dim feature scaling)
          and produces verified "AI Résumé-Job Match Fit" with classification threshold.
        - Mode B (Skills-Only Available): Computes embedding semantic similarity & skill coverage
          to produce transparent "Skills-Only Relevance" distinct from neural résumé fit.
        """
        inference_service = MLInferenceService.get_instance()
        encoder = inference_service.encoder
        vocab = inference_service.vocabulary

        # 1. Resolve Resume Context if provided
        resume_text = None
        if req.resume_text and len(req.resume_text.strip()) >= 20:
            resume_text = req.resume_text.strip()
        elif req.resume_id:
            res_obj = db.query(Resume).filter(Resume.id == req.resume_id).first()
            if res_obj and (not current_user or current_user.role != "candidate" or res_obj.user_id == current_user.id):
                resume_text = res_obj.raw_text

        # Deduplicate and normalize skills list
        user_skills: List[str] = [s.strip().lower() for s in req.skills if s and s.strip()]
        if resume_text:
            extracted = extract_skills(clean(resume_text, mask=True), vocab)
            # Combine provided skills with extracted skills
            user_skills = sorted(list(set(user_skills) | extracted))

        has_resume_context = bool(resume_text and len(resume_text.strip()) >= 20)

        # 2. Query Curated Database Jobs
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

        # Format DB jobs
        candidate_pool: List[Dict[str, Any]] = []
        for j in db_jobs:
            candidate_pool.append({
                "id": j.id,
                "job_code": j.job_code,
                "title": j.title,
                "company_name": j.company.name if j.company else "Verified Tech Partner",
                "location": j.location,
                "job_type": j.job_type,
                "experience_level": j.experience_level,
                "category": j.category,
                "description": j.description,
                "requirements": j.requirements or "See job specifications.",
                "min_salary": j.min_salary,
                "max_salary": j.max_salary,
                "salary_currency": j.salary_currency or "USD",
                "posted_date": j.created_at.strftime("%b %d, %Y") if j.created_at else None,
                "source_type": "curated_dataset",
                "source_label": "Curated Dataset Listing",
                "external_url": None,
                "full_text": f"{j.title} {j.category or ''}\n{j.description}\n{j.requirements or ''}"
            })

        # 3. Retrieve Live External Vacancies if requested
        api_status = ExternalJobService.get_api_status()
        if req.include_external:
            ext_jobs, api_status = ExternalJobService.fetch_jobs(
                skills=user_skills,
                location=req.location,
                job_type=req.job_type,
                limit=15
            )
            for ej in ext_jobs:
                # Apply filter checks on external jobs
                if req.category and req.category.lower() not in ej.get("category", "").lower():
                    continue
                if req.job_type and req.job_type.lower() != ej.get("job_type", "").lower():
                    continue
                ej["full_text"] = f"{ej['title']} {ej.get('category', '')}\n{ej.get('description', '')}"
                candidate_pool.append(ej)

        # 4. Deduplicate candidate pool
        seen_titles = set()
        deduped_pool = []
        for c in candidate_pool:
            sig = f"{c['title'].lower().strip()}::{c['company_name'].lower().strip()}"
            if sig not in seen_titles:
                seen_titles.add(sig)
                deduped_pool.append(c)

        if not deduped_pool:
            return SkillRecommendationResponse(
                total=0,
                page=(req.offset // req.limit) + 1 if req.limit else 1,
                limit=req.limit,
                active_skills=user_skills,
                has_resume_context=has_resume_context,
                api_status=api_status,
                items=[]
            )

        # 5. Retrieve User's Saved Job IDs for bookmark state
        saved_ids: Set[str] = set()
        if current_user:
            saved_records = db.query(SavedJob.job_id).filter(SavedJob.user_id == current_user.id).all()
            saved_ids = {r[0] for r in saved_records}

        # 6. Scoring and Ranking
        # Prepare candidate representation
        clean_resume_text = clean(resume_text, mask=True) if has_resume_context else None
        
        # Candidate skills embedding representation
        skills_text = f"Technical competencies and skills: {', '.join(user_skills)}" if user_skills else "Software engineer technical qualifications"
        clean_skills_text = clean(skills_text, mask=True)
        skills_emb = encoder.encode([clean_skills_text])[0]
        user_skills_set = set(user_skills)

        ranked_items: List[JobRecommendationItem] = []

        for candidate in deduped_pool:
            job_text = candidate["full_text"]
            clean_job = clean(job_text, mask=True)
            job_skills = extract_skills(clean_job, vocab)

            # Skill overlap
            matched_skills = sorted(list(user_skills_set & job_skills))
            missing_skills = sorted(list(job_skills - user_skills_set))
            overlap_ratio = float(len(matched_skills) / max(1, len(job_skills)))

            # Semantic similarity
            job_emb = encoder.encode([clean_job])[0]
            semantic_sim = float(np.dot(skills_emb, job_emb))
            semantic_sim = max(0.0, min(1.0, semantic_sim))

            if has_resume_context:
                # Mode A: Full Neural Inference with PyTorch MatchNetwork
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
                matched = pred["matched_skills"]
                missing = pred["missing_skills"]
                relevance_explanation = (
                    f"Neural alignment score: {score:.1f}% ({classification}). "
                    f"Matches {len(matched)} of {len(matched) + len(missing)} listed skills with "
                    f"{semantic_similarity * 100:.1f}% semantic similarity to role requirements."
                )
            else:
                # Mode B: Skills-Only Relevance Score
                # Weighted combination of semantic alignment (60%) and skill coverage (40%)
                relevance = (semantic_sim * 0.6 + overlap_ratio * 0.4) * 100.0
                score = round(min(100.0, max(0.0, relevance)), 1)
                score_type = "skills_only_relevance"
                score_label = "Skills-Only Relevance"
                if score >= 75:
                    classification = "High Skill Fit"
                elif score >= 50:
                    classification = "Moderate Skill Fit"
                else:
                    classification = "Low Skill Fit"

                semantic_similarity = round(semantic_sim, 4)
                skill_coverage = round(overlap_ratio, 4)
                matched = matched_skills
                missing = missing_skills
                relevance_explanation = (
                    f"Matches {len(matched)} of {len(job_skills)} listed competencies "
                    f"({', '.join(matched[:3]) if matched else 'general keywords'}) with "
                    f"{semantic_similarity * 100:.1f}% semantic relevance to role specifications."
                )

            is_saved = candidate["id"] in saved_ids if candidate.get("id") else False

            ranked_items.append(JobRecommendationItem(
                id=candidate.get("id"),
                job_code=candidate.get("job_code"),
                title=candidate["title"],
                company_name=candidate["company_name"],
                location=candidate["location"],
                job_type=candidate["job_type"],
                experience_level=candidate.get("experience_level"),
                category=candidate.get("category"),
                description=candidate.get("description"),
                min_salary=candidate.get("min_salary"),
                max_salary=candidate.get("max_salary"),
                salary_currency=candidate.get("salary_currency", "USD"),
                posted_date=candidate.get("posted_date"),
                source_type=candidate["source_type"],
                source_label=candidate["source_label"],
                external_url=candidate.get("external_url"),
                score=score,
                score_type=score_type,
                score_label=score_label,
                classification=classification,
                semantic_similarity=semantic_similarity,
                skill_coverage=skill_coverage,
                matched_skills=matched,
                missing_skills=missing,
                relevance_explanation=relevance_explanation,
                is_saved=is_saved
            ))

        # Sort by relevance / compatibility score descending
        ranked_items.sort(key=lambda x: x.score, reverse=True)

        total_count = len(ranked_items)
        paginated = ranked_items[req.offset: req.offset + req.limit]
        current_page = (req.offset // req.limit) + 1 if req.limit else 1

        return SkillRecommendationResponse(
            total=total_count,
            page=current_page,
            limit=req.limit,
            active_skills=user_skills,
            has_resume_context=has_resume_context,
            api_status=api_status,
            items=paginated
        )

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
        """Legacy helper for backward compatibility."""
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
