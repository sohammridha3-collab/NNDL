from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import (
    Application,
    Job,
    JobSkill,
    MatchingResult,
    Resume,
    SavedJob,
    User
)
from app.schemas.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    JobCreate,
    JobResponse,
    JobUpdate
)
from app.services.matching_service import MatchingService

router = APIRouter(prefix="/jobs", tags=["Jobs"])

APPLICATION_STATUSES = {"applied", "under_review", "shortlisted", "interviewed", "offered", "rejected"}
JOB_SORTS = {
    "newest": Job.created_at.desc(),
    "oldest": Job.created_at.asc(),
    "title": Job.title.asc(),
}


def _job_to_response(j: Job) -> JobResponse:
    return JobResponse(
        id=j.id,
        job_code=j.job_code,
        title=j.title,
        category=j.category,
        description=j.description,
        requirements=j.requirements,
        location=j.location,
        job_type=j.job_type,
        experience_level=j.experience_level,
        min_salary=j.min_salary,
        max_salary=j.max_salary,
        salary_currency=j.salary_currency,
        status=j.status,
        company_name=j.company.name if j.company else "Verified Tech Partner",
        skills=[s.skill_name for s in j.skills],
        applicant_count=len(j.applications),
        created_at=j.created_at
    )


def _application_to_response(a: Application) -> ApplicationResponse:
    job = a.job
    return ApplicationResponse(
        id=a.id,
        job_id=a.job_id,
        candidate_id=a.candidate_id,
        resume_id=a.resume_id,
        candidate_name=a.user.full_name if a.user else "Candidate",
        candidate_email=a.user.email if a.user else "",
        job_title=job.title if job else "Role",
        company_name=job.company.name if job and job.company else None,
        status=a.status,
        stage=a.stage,
        match_score=a.match_score,
        cover_note=a.cover_note,
        recruiter_note=a.recruiter_note,
        created_at=a.created_at,
        updated_at=a.updated_at
    )


@router.get("/recruiter/mine", response_model=List[JobResponse])
def list_my_jobs(
    status: Optional[str] = Query("all", description="active, closed, or all"),
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """Recruiter: list job postings owned by the current user (all statuses by default)."""
    query = db.query(Job).filter(Job.recruiter_id == current_user.id)
    if status and status != "all":
        query = query.filter(Job.status == status)
    return [_job_to_response(j) for j in query.order_by(Job.created_at.desc()).all()]


@router.get("/applications/mine", response_model=List[ApplicationResponse])
def list_my_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Candidate: list every application submitted by the current user."""
    apps = db.query(Application).filter(
        Application.candidate_id == current_user.id
    ).order_by(Application.created_at.desc()).all()

    updated = False
    for a in apps:
        if a.match_score is None:
            latest_match = db.query(MatchingResult).filter(
                MatchingResult.candidate_id == a.candidate_id,
                MatchingResult.job_id == a.job_id
            ).order_by(MatchingResult.created_at.desc()).first()
            if latest_match:
                a.match_score = latest_match.compatibility_score
                updated = True
    if updated:
        db.commit()

    return [_application_to_response(a) for a in apps]


@router.get("/saved/mine", response_model=List[JobResponse])
def list_my_saved_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Candidate: list bookmarked jobs."""
    saved = db.query(SavedJob).filter(
        SavedJob.user_id == current_user.id
    ).order_by(SavedJob.created_at.desc()).all()
    return [_job_to_response(s.job) for s in saved if s.job is not None]


@router.get("", response_model=List[JobResponse])
def list_jobs(
    q: Optional[str] = Query(None, description="Search keyword in title or description"),
    category: Optional[str] = Query(None, description="Filter by job category"),
    job_type: Optional[str] = Query(None, description="remote, hybrid, or on-site"),
    location: Optional[str] = Query(None, description="Filter by location"),
    status: Optional[str] = Query("active", description="active, closed, or all"),
    sort: str = Query("newest", description="newest, oldest, or title"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Browse and search job opportunities with comprehensive filtering."""
    query = db.query(Job)
    if status != "all":
        query = query.filter(Job.status == status)
    if q:
        query = query.filter((Job.title.ilike(f"%{q}%")) | (Job.description.ilike(f"%{q}%")))
    if category:
        query = query.filter(Job.category.ilike(f"%{category}%"))
    if job_type:
        query = query.filter(Job.job_type == job_type)
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))

    order = JOB_SORTS.get(sort, JOB_SORTS["newest"])
    jobs = query.order_by(order, Job.id).offset(offset).limit(limit).all()

    results = []
    for j in jobs:
        results.append(JobResponse(
            id=j.id,
            job_code=j.job_code,
            title=j.title,
            category=j.category,
            description=j.description,
            requirements=j.requirements,
            location=j.location,
            job_type=j.job_type,
            experience_level=j.experience_level,
            min_salary=j.min_salary,
            max_salary=j.max_salary,
            salary_currency=j.salary_currency,
            status=j.status,
            company_name=j.company.name if j.company else "Verified Tech Partner",
            skills=[s.skill_name for s in j.skills],
            applicant_count=len(j.applications),
            created_at=j.created_at
        ))
    return results


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    job_in: JobCreate,
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """Post a new job opening (Recruiters and Admins only)."""
    company_id = current_user.recruiter_profile.company_id if current_user.recruiter_profile else None
    
    new_job = Job(
        recruiter_id=current_user.id,
        company_id=company_id,
        title=job_in.title,
        category=job_in.category,
        description=job_in.description,
        requirements=job_in.requirements,
        location=job_in.location,
        job_type=job_in.job_type,
        experience_level=job_in.experience_level,
        min_salary=job_in.min_salary,
        max_salary=job_in.max_salary,
        salary_currency=job_in.salary_currency,
        status="active"
    )
    db.add(new_job)
    db.flush()

    for sk in job_in.skills:
        db.add(JobSkill(job_id=new_job.id, skill_name=sk, is_required=True))

    db.commit()
    db.refresh(new_job)

    return JobResponse(
        id=new_job.id,
        job_code=new_job.job_code,
        title=new_job.title,
        category=new_job.category,
        description=new_job.description,
        requirements=new_job.requirements,
        location=new_job.location,
        job_type=new_job.job_type,
        experience_level=new_job.experience_level,
        min_salary=new_job.min_salary,
        max_salary=new_job.max_salary,
        salary_currency=new_job.salary_currency,
        status=new_job.status,
        company_name=new_job.company.name if new_job.company else "Verified Tech Partner",
        skills=[s.skill_name for s in new_job.skills],
        applicant_count=0,
        created_at=new_job.created_at
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Retrieve details of a single job opening."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job opening not found.")
    return JobResponse(
        id=job.id,
        job_code=job.job_code,
        title=job.title,
        category=job.category,
        description=job.description,
        requirements=job.requirements,
        location=job.location,
        job_type=job.job_type,
        experience_level=job.experience_level,
        min_salary=job.min_salary,
        max_salary=job.max_salary,
        salary_currency=job.salary_currency,
        status=job.status,
        company_name=job.company.name if job.company else "Verified Tech Partner",
        skills=[s.skill_name for s in job.skills],
        applicant_count=len(job.applications),
        created_at=job.created_at
    )


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: str,
    job_in: JobUpdate,
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """Update job posting details."""
    query = db.query(Job).filter(Job.id == job_id)
    if current_user.role != "admin":
        query = query.filter(Job.recruiter_id == current_user.id)
    job = query.first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or unauthorized.")

    for field, val in job_in.model_dump(exclude_unset=True).items():
        if field == "skills" and val is not None:
            db.query(JobSkill).filter(JobSkill.job_id == job.id).delete()
            for s in val:
                db.add(JobSkill(job_id=job.id, skill_name=s))
        elif hasattr(job, field):
            setattr(job, field, val)

    db.commit()
    db.refresh(job)
    return JobResponse(
        id=job.id,
        job_code=job.job_code,
        title=job.title,
        category=job.category,
        description=job.description,
        requirements=job.requirements,
        location=job.location,
        job_type=job.job_type,
        experience_level=job.experience_level,
        min_salary=job.min_salary,
        max_salary=job.max_salary,
        salary_currency=job.salary_currency,
        status=job.status,
        company_name=job.company.name if job.company else "Verified Tech Partner",
        skills=[s.skill_name for s in job.skills],
        applicant_count=len(job.applications),
        created_at=job.created_at
    )


@router.delete("/{job_id}")
def delete_job(
    job_id: str,
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """Close or archive a job post."""
    query = db.query(Job).filter(Job.id == job_id)
    if current_user.role != "admin":
        query = query.filter(Job.recruiter_id == current_user.id)
    job = query.first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or unauthorized.")

    job.status = "closed"
    db.commit()
    return {"message": "Job successfully closed."}


@router.post("/{job_id}/apply", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def apply_to_job(
    job_id: str,
    app_in: ApplicationCreate,
    current_user: User = Depends(require_role(["candidate"])),
    db: Session = Depends(get_db)
):
    """Candidate submits application with resume and automatically generates AI match score."""
    job = db.query(Job).filter(Job.id == job_id, Job.status == "active").first()
    if not job:
        raise HTTPException(status_code=404, detail="Active job not found.")

    existing_app = db.query(Application).filter(
        Application.job_id == job_id,
        Application.candidate_id == current_user.id
    ).first()
    if existing_app:
        raise HTTPException(status_code=400, detail="You have already applied for this position.")

    # Locate resume
    resume_id = app_in.resume_id
    if not resume_id:
        active_resume = db.query(Resume).filter(
            Resume.user_id == current_user.id,
            Resume.is_active == True
        ).first()
        if not active_resume:
            raise HTTPException(status_code=400, detail="Please upload a resume first before applying.")
        resume_id = active_resume.id

    # Compute live match score using real ML model
    match_result = MatchingService.match_resume_and_job(
        db=db,
        resume_id=resume_id,
        job_id=job_id,
        current_user=current_user
    )

    application = Application(
        job_id=job_id,
        candidate_id=current_user.id,
        resume_id=resume_id,
        status="applied",
        stage="Applied",
        match_score=match_result.get("compatibility_score"),
        cover_note=app_in.cover_note
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    return ApplicationResponse(
        id=application.id,
        job_id=application.job_id,
        candidate_id=application.candidate_id,
        resume_id=application.resume_id,
        candidate_name=current_user.full_name,
        candidate_email=current_user.email,
        job_title=job.title,
        company_name=job.company.name if job.company else None,
        status=application.status,
        stage=application.stage,
        match_score=application.match_score,
        cover_note=application.cover_note,
        recruiter_note=application.recruiter_note,
        created_at=application.created_at,
        updated_at=application.updated_at
    )


@router.post("/{job_id}/save")
def toggle_save_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Candidate bookmarks or un-bookmarks a job."""
    if not db.query(Job.id).filter(Job.id == job_id).first():
        raise HTTPException(status_code=404, detail="Job opening not found.")
    saved = db.query(SavedJob).filter(
        SavedJob.job_id == job_id,
        SavedJob.user_id == current_user.id
    ).first()

    if saved:
        db.delete(saved)
        db.commit()
        return {"saved": False, "message": "Job removed from saved list."}
    else:
        new_save = SavedJob(job_id=job_id, user_id=current_user.id)
        db.add(new_save)
        db.commit()
        return {"saved": True, "message": "Job successfully saved."}


@router.post("/save-external", status_code=status.HTTP_201_CREATED)
def save_external_job(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Persists an external live vacancy to the database and bookmarks it
    under the authenticated user.
    """
    ext_id = payload.get("id") or payload.get("job_code") or payload.get("external_id")
    if not ext_id:
        raise HTTPException(status_code=400, detail="External job ID is required.")

    # Check if job already exists in DB
    job = db.query(Job).filter((Job.id == ext_id) | (Job.job_code == ext_id)).first()
    if not job:
        # Create company if needed
        comp_name = payload.get("company_name", "Verified Employer").strip()
        from app.models.models import Company
        company = db.query(Company).filter(Company.name == comp_name).first()
        if not company:
            company = Company(name=comp_name, location=payload.get("location", "Remote"))
            db.add(company)
            db.flush()

        job = Job(
            id=ext_id,
            job_code=ext_id,
            company_id=company.id,
            title=payload.get("title", "Software Engineer"),
            category=payload.get("category", "Software & Engineering"),
            description=payload.get("description", "External job listing."),
            requirements=payload.get("requirements", "See original posting for details."),
            location=payload.get("location", "Remote"),
            job_type=payload.get("job_type", "remote"),
            experience_level=payload.get("experience_level", "Mid-Level"),
            min_salary=payload.get("min_salary"),
            max_salary=payload.get("max_salary"),
            salary_currency=payload.get("salary_currency", "USD"),
            status="active"
        )
        db.add(job)
        db.flush()

    saved = db.query(SavedJob).filter(
        SavedJob.job_id == job.id,
        SavedJob.user_id == current_user.id
    ).first()

    if saved:
        db.delete(saved)
        db.commit()
        return {
            "saved": False,
            "job_id": job.id,
            "title": job.title,
            "is_external": True,
            "external_url": payload.get("external_url"),
            "message": "Job removed from saved list."
        }
    else:
        new_save = SavedJob(job_id=job.id, user_id=current_user.id)
        db.add(new_save)
        db.commit()
        return {
            "saved": True,
            "job_id": job.id,
            "title": job.title,
            "is_external": True,
            "external_url": payload.get("external_url"),
            "message": "External vacancy successfully bookmarked."
        }



@router.get("/{job_id}/applicants", response_model=List[ApplicationResponse])
def get_job_applicants(
    job_id: str,
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """
    Recruiters view applicants ranked by real AI matching score.
    Respects human review: does not automatically filter out candidates.
    """
    query = db.query(Job).filter(Job.id == job_id)
    if current_user.role != "admin":
        query = query.filter(Job.recruiter_id == current_user.id)
    job = query.first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or unauthorized.")

    applications = db.query(Application).filter(Application.job_id == job_id).all()

    # Sort applicants by AI match score descending (supporting human review)
    sorted_apps = sorted(applications, key=lambda a: (a.match_score or 0.0), reverse=True)

    return [
        ApplicationResponse(
            id=a.id,
            job_id=a.job_id,
            candidate_id=a.candidate_id,
            resume_id=a.resume_id,
            candidate_name=a.user.full_name if a.user else "Candidate",
            candidate_email=a.user.email if a.user else "",
            job_title=job.title,
            company_name=job.company.name if job.company else None,
            status=a.status,
            stage=a.stage,
            match_score=a.match_score,
            cover_note=a.cover_note,
            recruiter_note=a.recruiter_note,
            created_at=a.created_at,
            updated_at=a.updated_at
        )
        for a in sorted_apps
    ]


@router.put("/{job_id}/applicants/{app_id}", response_model=ApplicationResponse)
def update_applicant_stage(
    job_id: str,
    app_id: str,
    update_in: ApplicationUpdate,
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """Recruiters manage candidate recruitment stages and private notes."""
    app = db.query(Application).filter(
        Application.id == app_id,
        Application.job_id == job_id
    ).first()
    # Recruiters may only manage applicants of their own job postings.
    if app and current_user.role != "admin" and (not app.job or app.job.recruiter_id != current_user.id):
        app = None
    if not app:
        raise HTTPException(status_code=404, detail="Application record not found.")

    if update_in.status and update_in.status not in APPLICATION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{update_in.status}'. Allowed: {', '.join(sorted(APPLICATION_STATUSES))}."
        )

    if update_in.status:
        app.status = update_in.status
    if update_in.stage:
        app.stage = update_in.stage
    if update_in.recruiter_note is not None:
        app.recruiter_note = update_in.recruiter_note

    db.commit()
    db.refresh(app)

    return ApplicationResponse(
        id=app.id,
        job_id=app.job_id,
        candidate_id=app.candidate_id,
        resume_id=app.resume_id,
        candidate_name=app.user.full_name if app.user else "Candidate",
        candidate_email=app.user.email if app.user else "",
        job_title=app.job.title if app.job else "Role",
        company_name=app.job.company.name if app.job and app.job.company else None,
        status=app.status,
        stage=app.stage,
        match_score=app.match_score,
        cover_note=app.cover_note,
        recruiter_note=app.recruiter_note,
        created_at=app.created_at,
        updated_at=app.updated_at
    )
