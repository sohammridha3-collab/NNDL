from typing import Any, Dict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    Application,
    FairnessAudit,
    Job,
    MatchingResult,
    Resume,
    SavedJob,
    User
)


class DashboardService:
    @staticmethod
    def get_candidate_dashboard(db: Session, user: User) -> Dict[str, Any]:
        active_resume = db.query(Resume).filter(
            Resume.user_id == user.id,
            Resume.is_active == True
        ).first()

        applications = db.query(Application).filter(
            Application.candidate_id == user.id
        ).order_by(Application.created_at.desc()).all()

        saved_jobs_count = db.query(SavedJob).filter(SavedJob.user_id == user.id).count()

        profile_comp = user.candidate_profile.profile_completion if user.candidate_profile else 40.0

        apps_data = []
        for app in applications[:10]:
            apps_data.append({
                "id": app.id,
                "job_id": app.job_id,
                "job_title": app.job.title if app.job else "Position",
                "company_name": app.job.company.name if app.job and app.job.company else "Tech Partner",
                "status": app.status,
                "stage": app.stage,
                "match_score": app.match_score,
                "applied_at": app.created_at
            })

        recent_activity = [
            {"type": "application", "text": f"Applied for {a['job_title']}", "time": a["applied_at"]}
            for a in apps_data[:3]
        ]
        
        active_resume_data = None
        if active_resume:
            recent_activity.insert(0, {
                "type": "resume",
                "text": f"Uploaded resume '{active_resume.file_name}' (ATS Score: {active_resume.ats_score}%)",
                "time": active_resume.created_at
            })
            active_resume_data = {
                "id": active_resume.id,
                "user_id": active_resume.user_id,
                "file_name": active_resume.file_name,
                "file_type": active_resume.file_type,
                "file_size_bytes": active_resume.file_size_bytes,
                "version": active_resume.version,
                "is_active": active_resume.is_active,
                "ats_score": active_resume.ats_score,
                "completeness_score": active_resume.completeness_score,
                "skills": [s.skill_name for s in active_resume.skills] if active_resume.skills else [],
                "created_at": active_resume.created_at,
                "updated_at": active_resume.updated_at
            }

        return {
            "active_resume": active_resume_data,
            "total_applications": len(applications),
            "applications": apps_data,
            "saved_jobs_count": saved_jobs_count,
            "top_recommended_jobs": [],
            "profile_completion": profile_comp,
            "recent_activity": recent_activity
        }

    @staticmethod
    def get_recruiter_dashboard(db: Session, user: User) -> Dict[str, Any]:
        jobs = db.query(Job).filter(Job.recruiter_id == user.id).order_by(Job.created_at.desc()).all()
        job_ids = [j.id for j in jobs]

        total_active_jobs = sum(1 for j in jobs if j.status == "active")
        
        applications = db.query(Application).filter(Application.job_id.in_(job_ids)).all() if job_ids else []
        total_applicants = len(applications)

        # Pipeline stages count
        stages_count = {
            "applied": 0,
            "under_review": 0,
            "shortlisted": 0,
            "interviewed": 0,
            "offered": 0,
            "rejected": 0
        }
        for app in applications:
            if app.status in stages_count:
                stages_count[app.status] += 1
            else:
                stages_count["applied"] += 1

        recent_jobs = [
            {
                "id": j.id,
                "title": j.title,
                "category": j.category,
                "status": j.status,
                "applicant_count": len(j.applications),
                "created_at": j.created_at
            }
            for j in jobs[:5]
        ]

        recent_applicants = [
            {
                "id": app.id,
                "candidate_name": app.user.full_name if app.user else "Candidate",
                "job_title": app.job.title if app.job else "Role",
                "status": app.status,
                "match_score": app.match_score,
                "created_at": app.created_at
            }
            for app in sorted(applications, key=lambda a: a.created_at, reverse=True)[:5]
        ]

        hiring_trends = [
            {"stage": "Applications", "count": total_applicants},
            {"stage": "Under Review", "count": stages_count["under_review"]},
            {"stage": "Shortlisted", "count": stages_count["shortlisted"]},
            {"stage": "Interviews", "count": stages_count["interviewed"]},
            {"stage": "Offers", "count": stages_count["offered"]}
        ]

        return {
            "total_active_jobs": total_active_jobs,
            "total_applicants": total_applicants,
            "recent_jobs": recent_jobs,
            "recent_applicants": recent_applicants,
            "pipeline_stages_count": stages_count,
            "hiring_trends": hiring_trends
        }

    @staticmethod
    def get_admin_dashboard(db: Session) -> Dict[str, Any]:
        total_users = db.query(User).count()
        total_candidates = db.query(User).filter(User.role == "candidate").count()
        total_recruiters = db.query(User).filter(User.role == "recruiter").count()
        total_jobs = db.query(Job).count()
        total_applications = db.query(Application).count()
        total_matches_run = db.query(MatchingResult).count()

        latest_fairness = db.query(FairnessAudit).order_by(FairnessAudit.created_at.desc()).first()
        latest_summary = {}
        if latest_fairness and isinstance(latest_fairness.metrics, dict):
            latest_summary = latest_fairness.metrics.get("summary", {}) or {}
        fairness_summary = {
            "audits_completed": db.query(FairnessAudit).count(),
            "latest_audit_date": latest_fairness.created_at if latest_fairness else None,
            "sdg10_status": "Active - Irrelevant demographic indicators masked before matching",
            # Values below are read from the most recent persisted audit; None when no audit exists.
            "latest_masked_mean_score_change": latest_summary.get("masked_mean_score_deviation"),
            "latest_unmasked_mean_score_change": latest_summary.get("unmasked_mean_score_deviation"),
            "latest_masked_flip_rate": latest_summary.get("decision_flip_rate_with_masking"),
            "latest_sample_pairs": latest_summary.get("evaluation_sample_pairs"),
        }

        from app.ml.inference import MLInferenceService
        ml_loaded = MLInferenceService._instance is not None
        system_health = {
            "api_status": "Healthy",
            "model_status": "Loaded" if ml_loaded else "Not loaded yet",
            "database_status": "Connected",
            "encoder": "sentence-transformers/all-MiniLM-L6-v2",
            "classifier": "PyTorch MatchNetwork (770 features)",
            "device": "cpu"
        }

        return {
            "total_users": total_users,
            "total_candidates": total_candidates,
            "total_recruiters": total_recruiters,
            "total_jobs": total_jobs,
            "total_applications": total_applications,
            "total_matches_run": total_matches_run,
            "fairness_summary": fairness_summary,
            "system_health": system_health
        }
