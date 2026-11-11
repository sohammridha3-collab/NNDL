from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import Resume, User
from app.schemas.schemas import ResumeAnalysisResponse, ResumeResponse
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/resumes", tags=["Resumes"])


@router.post("/upload", response_model=ResumeResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a resume file (PDF, DOCX, or TXT).
    Extracts text, identifies sections, calculates ATS score, and stores extracted skills.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    resume = ResumeService.process_and_save_resume(
        db=db,
        user=current_user,
        file_bytes=contents,
        filename=file.filename or "resume.pdf"
    )

    skill_names = [s.skill_name for s in resume.skills]
    return ResumeResponse(
        id=resume.id,
        user_id=resume.user_id,
        file_name=resume.file_name,
        file_type=resume.file_type,
        file_size_bytes=resume.file_size_bytes,
        version=resume.version,
        is_active=resume.is_active,
        ats_score=resume.ats_score,
        completeness_score=resume.completeness_score,
        skills=skill_names,
        created_at=resume.created_at,
        updated_at=resume.updated_at
    )


@router.get("", response_model=List[ResumeResponse])
def list_resumes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all resumes uploaded by the current user."""
    resumes = ResumeService.get_candidate_resumes(db, current_user.id)
    return [
        ResumeResponse(
            id=r.id,
            user_id=r.user_id,
            file_name=r.file_name,
            file_type=r.file_type,
            file_size_bytes=r.file_size_bytes,
            version=r.version,
            is_active=r.is_active,
            ats_score=r.ats_score,
            completeness_score=r.completeness_score,
            skills=[s.skill_name for s in r.skills],
            created_at=r.created_at,
            updated_at=r.updated_at
        )
        for r in resumes
    ]


@router.get("/{resume_id}", response_model=ResumeResponse)
def get_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific resume."""
    resume = ResumeService.get_resume(db, resume_id, user_id=current_user.id if current_user.role != "admin" else None)
    return ResumeResponse(
        id=resume.id,
        user_id=resume.user_id,
        file_name=resume.file_name,
        file_type=resume.file_type,
        file_size_bytes=resume.file_size_bytes,
        version=resume.version,
        is_active=resume.is_active,
        ats_score=resume.ats_score,
        completeness_score=resume.completeness_score,
        skills=[s.skill_name for s in resume.skills],
        created_at=resume.created_at,
        updated_at=resume.updated_at
    )


@router.delete("/{resume_id}")
def delete_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a resume and its physical file."""
    ResumeService.delete_resume(db, resume_id, current_user.id)
    return {"message": "Resume deleted successfully."}


@router.post("/{resume_id}/analyze", response_model=ResumeAnalysisResponse)
def analyze_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Perform deep ATS readability, section, and skill completeness analysis on an uploaded resume.
    """
    resume = ResumeService.get_resume(db, resume_id, user_id=current_user.id if current_user.role != "admin" else None)
    details = resume.analysis_details or {}
    
    rating = (
        "Excellent" if resume.ats_score >= 85
        else "Good" if resume.ats_score >= 70
        else "Needs Improvement"
    )

    strengths = [
        f"Detected {len(resume.skills)} validated technical skill keywords.",
        f"Resume parsed cleanly with {len(resume.raw_text.split())} words."
    ]

    return ResumeAnalysisResponse(
        resume_id=resume.id,
        ats_score=resume.ats_score,
        completeness_score=resume.completeness_score,
        readability_rating=rating,
        extracted_skills=[s.skill_name for s in resume.skills],
        identified_sections=details.get("identified_sections", []),
        missing_critical_sections=details.get("missing_critical_sections", []),
        strengths=strengths,
        improvement_recommendations=details.get("recommendations", []),
        sdg10_bias_mitigation_applied=True
    )
