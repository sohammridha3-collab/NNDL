from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user, require_role
from app.db.session import get_db
from app.models.models import Job, Resume, User
from app.schemas.schemas import (
    ResumeProfileSummaryRequest,
    ResumeProfileSummaryResponse,
    SkillExtractionRequest,
    SkillExtractionResponse,
    SkillRecommendationRequest,
    SkillRecommendationResponse
)
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.post("/profile-summary", response_model=ResumeProfileSummaryResponse)
def get_resume_profile_summary(
    request: ResumeProfileSummaryRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Parses an uploaded or stored résumé into a confirmed, editable profile summary:
    - Identifies scanned/unreadable documents and provides recovery instructions.
    - Extracts skills, non-overlapping employment tenure, and possible role titles.
    - Previews candidate qualifications before initiating focused job search queries.
    """
    return RecommendationService.extract_profile_summary_from_resume(
        db=db,
        request=request,
        current_user=current_user
    )


@router.post("/skills", response_model=SkillRecommendationResponse)
def get_recommendations_by_skills(
    request: SkillRecommendationRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Skill-based job recommendation engine.
    - Evaluates entered skill chips or extracts from selected résumé.
    - Connects curated database listings and authorized live vacancies (Adzuna / Remotive).
    - Distinguishes Skills-Only Relevance vs. Full Neural Résumé Match Fit.
    """
    return RecommendationService.recommend_jobs_by_skills(
        db=db,
        req=request,
        current_user=current_user
    )


@router.post("/extract-skills", response_model=SkillExtractionResponse)
def extract_skills_from_resume(
    request: SkillExtractionRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Extracts canonical skill tags from an existing stored resume or direct pasted text.
    Allows candidates to review, add, edit, and remove skills as interactive chips.
    """
    return RecommendationService.extract_skills_from_input(
        db=db,
        request=request,
        current_user=current_user
    )


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
