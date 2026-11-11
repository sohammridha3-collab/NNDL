import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.inference import MLInferenceService
from app.models.models import Application, Job, MatchingResult, Resume, User

logger = logging.getLogger("inclusive_ats.matching_service")


class MatchingService:
    @staticmethod
    def match_resume_and_job(
        db: Session,
        resume_id: Optional[str] = None,
        job_id: Optional[str] = None,
        resume_text: Optional[str] = None,
        job_text: Optional[str] = None,
        current_user: Optional[User] = None
    ) -> Dict[str, Any]:
        inference_service = MLInferenceService.get_instance()

        # Input precedence: Pasted text takes precedence if provided and non-empty (>= 20 chars).
        # Otherwise, resolve from database via ID or user's active resume.
        resolved_resume_id = None
        resolved_resume_text = None
        resume_obj = None

        if resume_text and len(resume_text.strip()) >= 20:
            resolved_resume_text = resume_text.strip()
            if resume_id:
                resume_obj = db.query(Resume).filter(Resume.id == resume_id).first()
                if resume_obj:
                    resolved_resume_id = resume_obj.id
        elif resume_id:
            resume_obj = db.query(Resume).filter(Resume.id == resume_id).first()
            # Candidates may only analyze their own stored resumes.
            if resume_obj and current_user and current_user.role == "candidate" and resume_obj.user_id != current_user.id:
                resume_obj = None
            if not resume_obj:
                raise HTTPException(status_code=404, detail=f"Resume with id '{resume_id}' not found.")
            if not resume_obj.raw_text or not resume_obj.raw_text.strip():
                raise HTTPException(status_code=400, detail="The selected resume contains no extracted text content.")
            resolved_resume_id = resume_obj.id
            resolved_resume_text = resume_obj.raw_text
        elif current_user:
            # Fall back to user's active resume
            resume_obj = db.query(Resume).filter(
                Resume.user_id == current_user.id,
                Resume.is_active == True
            ).first()
            if resume_obj and resume_obj.raw_text and resume_obj.raw_text.strip():
                resolved_resume_id = resume_obj.id
                resolved_resume_text = resume_obj.raw_text

        # Job resolution
        resolved_job_id = None
        resolved_job_text = None
        job_obj = None

        if job_text and len(job_text.strip()) >= 20:
            resolved_job_text = job_text.strip()
            if job_id:
                job_obj = db.query(Job).filter(Job.id == job_id).first()
                if job_obj:
                    resolved_job_id = job_obj.id
        elif job_id:
            job_obj = db.query(Job).filter(Job.id == job_id).first()
            if not job_obj:
                raise HTTPException(status_code=404, detail=f"Job with id '{job_id}' not found.")
            resolved_job_id = job_obj.id
            resolved_job_text = f"{job_obj.title}\n{job_obj.description}\n{job_obj.requirements or ''}".strip()
            if not resolved_job_text:
                raise HTTPException(status_code=400, detail="The selected job post contains no description text.")

        if not resolved_resume_text or len(resolved_resume_text.strip()) < 20:
            raise HTTPException(
                status_code=400,
                detail="Resume content is required. Please select an uploaded resume or paste at least 20 characters of resume text."
            )

        if not resolved_job_text or len(resolved_job_text.strip()) < 20:
            raise HTTPException(
                status_code=400,
                detail="Job description is required. Please select a posted job opening or paste at least 20 characters of job description."
            )

        # Run Real Model Inference
        mask_bias = settings.ENABLE_BIAS_MASKING
        prediction = inference_service.predict_pair(
            resume_text=resolved_resume_text,
            job_text=resolved_job_text,
            mask=mask_bias
        )

        # Attribute the result to the resume owner when a stored resume is used
        # (e.g. a recruiter re-scoring an applicant), otherwise to the requester.
        candidate_user_id = resume_obj.user_id if resume_obj else (current_user.id if current_user else None)

        # Persist MatchingResult if both records exist in DB
        matching_record = None
        if resolved_job_id:
            matching_record = MatchingResult(
                candidate_id=candidate_user_id,
                job_id=resolved_job_id,
                resume_id=resolved_resume_id,
                compatibility_score=prediction["compatibility_score"],
                score_type=prediction["score_type"],
                classification=prediction["classification"],
                decision_threshold=prediction["decision_threshold"],
                semantic_similarity=prediction["semantic_similarity"],
                required_skill_coverage=prediction["required_skill_coverage"],
                matched_skills=prediction["matched_skills"],
                missing_skills=prediction["missing_skills"],
                explanation=prediction["explanation"],
                model_version=prediction["model_version"]
            )
            db.add(matching_record)

            # Update match_score on existing application if present
            if candidate_user_id and resolved_job_id:
                app = db.query(Application).filter(
                    Application.candidate_id == candidate_user_id,
                    Application.job_id == resolved_job_id
                ).first()
                if app:
                    app.match_score = prediction["compatibility_score"]

            db.commit()

        return {
            "candidate_id": candidate_user_id,
            "job_id": resolved_job_id,
            **prediction,
            "id": matching_record.id if matching_record is not None else None,
            "resume_id": resolved_resume_id,
            "job_title": job_obj.title if job_obj else None,
            "created_at": matching_record.created_at if matching_record is not None else None,
        }

    @staticmethod
    def get_candidate_matching_history(db: Session, candidate_id: str, limit: int = 20) -> List[MatchingResult]:
        return db.query(MatchingResult).filter(
            MatchingResult.candidate_id == candidate_id
        ).order_by(MatchingResult.created_at.desc()).limit(limit).all()
