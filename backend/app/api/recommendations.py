from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import Job, Resume, User
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/jobs")
def get_job_recommendations(
    limit: int = Query(10, ge=1, le=20, description="Top 5, 10, or 20 recommendations"),
    category: Optional[str] = Query(None, description="Filter by category"),
    job_type: Optional[str] = Query(None, description="remote, hybrid, on-site"),
    location: Optional[str] = Query(None, description="Filter by location"),
    min_salary: Optional[float] = Query(None, description="Minimum salary"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get personalized AI job recommendations for the authenticated candidate
    based on their active resume embeddings, skill overlap, and neural reranking.
    """
    recommendations = RecommendationService.get_job_recommendations_for_user(
        db=db,
        user=current_user,
        top_k=limit,
        category=category,
        job_type=job_type,
        location=location,
        min_salary=min_salary
    )
    return {
        "candidate_id": current_user.id,
        "total_recommendations": len(recommendations),
        "recommendations": recommendations
    }


@router.get("/candidates")
def get_candidate_recommendations(
    job_id: str = Query(..., description="Job ID to find candidate matches for"),
    limit: int = Query(10, ge=1, le=20),
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """
    For recruiters: Get top candidates matching a specific job opening.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"job_id": job_id, "recommendations": []}

    from app.ml.inference import MLInferenceService
    inference_service = MLInferenceService.get_instance()
    job_full_text = f"{job.title} {job.category or ''}\n{job.description}"

    resumes = db.query(Resume).filter(Resume.is_active == True).limit(50).all()
    scored = []
    for r in resumes:
        pred = inference_service.predict_pair(
            resume_text=r.raw_text,
            job_text=job_full_text,
            mask=True
        )
        scored.append({
            "candidate_id": r.user_id,
            "candidate_name": r.user.full_name if r.user else "Candidate",
            "resume_id": r.id,
            "compatibility_score": pred["compatibility_score"],
            "classification": pred["classification"],
            "semantic_similarity": pred["semantic_similarity"],
            "required_skill_coverage": pred["required_skill_coverage"],
            "matched_skills": pred["matched_skills"],
            "missing_skills": pred["missing_skills"],
            "ats_score": r.ats_score
        })

    scored.sort(key=lambda x: x["compatibility_score"], reverse=True)
    return {
        "job_id": job_id,
        "job_title": job.title,
        "total_matches": len(scored[:limit]),
        "candidates": scored[:limit]
    }
