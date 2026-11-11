import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.preprocessing import clean, extract_skills, DEFAULT_SKILLS
from app.models.models import ExtractedSkill, Resume, User
from app.utils.file_extractor import (
    evaluate_resume_completeness,
    extract_resume_text,
    identify_sections
)


class ResumeService:
    @staticmethod
    def process_and_save_resume(
        db: Session,
        user: User,
        file_bytes: bytes,
        filename: str
    ) -> Resume:
        # Validate file size
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB."
            )

        # Extract text
        try:
            raw_text = extract_resume_text(file_bytes, filename)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Save physical file
        upload_path = Path(settings.UPLOAD_DIR) / str(user.id)
        upload_path.mkdir(parents=True, exist_ok=True)
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_disk_path = upload_path / unique_filename
        with open(file_disk_path, "wb") as f:
            f.write(file_bytes)

        # Run preprocessing and analysis
        cleaned_text = clean(raw_text, mask=False)
        anonymized_text = clean(raw_text, mask=True)
        sections = identify_sections(raw_text)
        ats_score, completeness, present_sections, missing_sections, recommendations = (
            evaluate_resume_completeness(raw_text, sections)
        )
        detected_skills = extract_skills(cleaned_text, DEFAULT_SKILLS)

        # Mark previously active resumes inactive
        db.query(Resume).filter(
            Resume.user_id == user.id,
            Resume.is_active == True
        ).update({"is_active": False})

        # Calculate version
        latest_res = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.version.desc()).first()
        version = (latest_res.version + 1) if latest_res else 1

        resume = Resume(
            user_id=user.id,
            file_name=filename,
            file_path=str(file_disk_path),
            file_type=filename.split(".")[-1].lower(),
            file_size_bytes=len(file_bytes),
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            anonymized_text=anonymized_text,
            version=version,
            is_active=True,
            ats_score=ats_score,
            completeness_score=completeness,
            extracted_sections=sections,
            analysis_details={
                "identified_sections": present_sections,
                "missing_critical_sections": missing_sections,
                "recommendations": recommendations,
                "word_count": len(raw_text.split()),
                "detected_skills_count": len(detected_skills)
            }
        )
        db.add(resume)
        db.flush()

        # Save extracted skills
        for sk in detected_skills:
            skill_entry = ExtractedSkill(
                resume_id=resume.id,
                skill_name=sk,
                category="Technical",
                confidence=1.0
            )
            db.add(skill_entry)

        # Update candidate profile completion
        if user.candidate_profile:
            user.candidate_profile.profile_completion = min(100.0, completeness)

        db.commit()
        db.refresh(resume)
        return resume

    @staticmethod
    def get_candidate_resumes(db: Session, user_id: str) -> List[Resume]:
        return db.query(Resume).filter(Resume.user_id == user_id).order_by(Resume.created_at.desc()).all()

    @staticmethod
    def get_resume(db: Session, resume_id: str, user_id: Optional[str] = None) -> Resume:
        query = db.query(Resume).filter(Resume.id == resume_id)
        if user_id:
            query = query.filter(Resume.user_id == user_id)
        resume = query.first()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found.")
        return resume

    @staticmethod
    def delete_resume(db: Session, resume_id: str, user_id: str) -> bool:
        resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user_id).first()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found or unauthorized.")
        
        # Delete file if exists
        try:
            if os.path.exists(resume.file_path):
                os.remove(resume.file_path)
        except Exception:
            pass

        db.delete(resume)
        db.commit()
        return True
