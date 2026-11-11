from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import MatchingResult, User
from app.schemas.schemas import (
    BatchMatchingRequest,
    MatchingRequest,
    MatchingResponse
)
from app.services.matching_service import MatchingService

router = APIRouter(prefix="/matching", tags=["AI Matching"])


@router.post("/predict", response_model=MatchingResponse)
def predict_match(
    request: MatchingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run real ML model inference to predict resume-job compatibility.
    Computes 770-dimensional feature vector, applies StandardScaler,
    and runs the PyTorch classifier. compatibility_score is the sigmoid
    probability on a 0-100 scale; decision_threshold is on the 0-1 scale.
    """
    result = MatchingService.match_resume_and_job(
        db=db,
        resume_id=request.resume_id,
        job_id=request.job_id,
        resume_text=request.resume_text,
        job_text=request.job_text,
        current_user=current_user
    )
    return result


@router.post("/batch")
def batch_match(
    request: BatchMatchingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Batch-match multiple resumes against a job description."""
    results = []
    for res_id in request.resume_ids:
        try:
            res = MatchingService.match_resume_and_job(
                db=db,
                resume_id=res_id,
                job_id=request.job_id,
                current_user=current_user
            )
            results.append(res)
        except Exception as e:
            results.append({
                "resume_id": res_id,
                "error": str(e)
            })
    return {"job_id": request.job_id, "results": results}


@router.get("/history", response_model=List[MatchingResponse])
def get_match_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve historical AI matching predictions for the current candidate."""
    history = MatchingService.get_candidate_matching_history(db, current_user.id)
    return [
        MatchingResponse(
            candidate_id=h.candidate_id,
            job_id=h.job_id,
            compatibility_score=h.compatibility_score,
            score_type=h.score_type,
            classification=h.classification,
            decision_threshold=h.decision_threshold,
            semantic_similarity=h.semantic_similarity,
            required_skill_coverage=h.required_skill_coverage,
            matched_skills=h.matched_skills or [],
            missing_skills=h.missing_skills or [],
            recommendations=h.explanation.get("recommendations", []) if isinstance(h.explanation, dict) else [],
            explanation=h.explanation or {},
            model_version=h.model_version,
            id=h.id,
            resume_id=h.resume_id,
            job_title=h.job.title if h.job else None,
            created_at=h.created_at
        )
        for h in history
    ]


@router.get("/{match_id}/explanation")
def get_match_explanation(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get transparent Explainable AI breakdown for a specific match record."""
    result = db.query(MatchingResult).filter(MatchingResult.id == match_id).first()
    if result and current_user.role == "candidate" and result.candidate_id != current_user.id:
        result = None
    if not result:
        raise HTTPException(status_code=404, detail="Matching record not found.")

    return {
        "match_id": result.id,
        "candidate_id": result.candidate_id,
        "job_id": result.job_id,
        "compatibility_score": result.compatibility_score,
        "classification": result.classification,
        "decision_threshold": result.decision_threshold,
        "semantic_similarity": result.semantic_similarity,
        "required_skill_coverage": result.required_skill_coverage,
        "matched_skills": result.matched_skills,
        "missing_skills": result.missing_skills,
        "model_version": result.model_version,
        "explanation": result.explanation
    }
