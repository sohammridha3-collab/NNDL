import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ml.embeddings import EmbeddingEncoder
from app.ml.inference import MLInferenceService
from app.ml.preprocessing import clean, extract_skills, DEFAULT_SKILLS
from app.models.models import Job, Resume, User

logger = logging.getLogger("inclusive_ats.recommendation_service")


class RecommendationService:
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
        # Retrieve candidate active resume
        resume = db.query(Resume).filter(
            Resume.user_id == user.id,
            Resume.is_active == True
        ).first()

        if not resume:
            # Fall back to latest resume
            resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.created_at.desc()).first()

        if not resume:
            return []

        # Query candidate jobs
        query = db.query(Job).filter(Job.status == "active")
        if category:
            query = query.filter(Job.category.ilike(f"%{category}%"))
        if job_type:
            query = query.filter(Job.job_type == job_type)
        if location:
            query = query.filter(Job.location.ilike(f"%{location}%"))
        if min_salary:
            query = query.filter(Job.max_salary >= min_salary)

        candidate_jobs = query.limit(50).all()
        if not candidate_jobs:
            return []

        inference_service = MLInferenceService.get_instance()
        encoder = inference_service.encoder

        # Candidate resume clean text & embedding
        clean_resume = clean(resume.raw_text, mask=True)
        resume_emb = encoder.encode([clean_resume])[0]
        resume_skills = extract_skills(clean_resume, inference_service.vocabulary)

        # Stage 1: Fast Vector Retrieval / Semantic Pruning
        scored_candidates = []
        for job in candidate_jobs:
            job_full_text = f"{job.title} {job.category or ''}\n{job.description}"
            clean_job = clean(job_full_text, mask=True)
            job_emb = encoder.encode([clean_job])[0]
            
            # Cosine similarity
            cosine_sim = float(np_dot(resume_emb, job_emb))
            
            # Skill overlap count
            job_skills = extract_skills(clean_job, inference_service.vocabulary)
            overlap = len(resume_skills & job_skills)
            
            # Combined retrieval score
            retrieval_score = (cosine_sim * 0.7) + (min(1.0, overlap / 5.0) * 0.3)
            scored_candidates.append((retrieval_score, job, job_full_text))

        # Sort top candidate jobs for neural reranking
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[:min(top_k * 2, 20)]

        # Stage 2: Real Model Neural Reranking on Top Candidates
        recommendations = []
        for _, job, job_text in top_candidates:
            pred = inference_service.predict_pair(
                resume_text=resume.raw_text,
                job_text=job_text,
                mask=True
            )
            recommendations.append({
                "job_id": job.id,
                "job_code": job.job_code,
                "title": job.title,
                "category": job.category,
                "company_name": job.company.name if job.company else "Verified Employer",
                "location": job.location,
                "job_type": job.job_type,
                "experience_level": job.experience_level,
                "min_salary": job.min_salary,
                "max_salary": job.max_salary,
                "salary_currency": job.salary_currency,
                "compatibility_score": pred["compatibility_score"],
                "classification": pred["classification"],
                "semantic_similarity": pred["semantic_similarity"],
                "required_skill_coverage": pred["required_skill_coverage"],
                "matched_skills": pred["matched_skills"],
                "missing_skills": pred["missing_skills"],
                "recommendation_reason": (
                    f"Strong alignment ({pred['compatibility_score']}%) with matched skills: " +
                    f"{', '.join(pred['matched_skills'][:3]) if pred['matched_skills'] else 'domain requirements'}."
                )
            })

        # Final sort by real compatibility score
        recommendations.sort(key=lambda x: x["compatibility_score"], reverse=True)
        return recommendations[:top_k]


def np_dot(a, b):
    import numpy as np
    return float(np.dot(a, b))
