from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import (
    AdminDashboardResponse,
    CandidateDashboardResponse,
    RecruiterDashboardResponse
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/candidate", response_model=CandidateDashboardResponse)
def get_candidate_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve personalized metrics and applications for candidate dashboard."""
    return DashboardService.get_candidate_dashboard(db, current_user)


@router.get("/recruiter", response_model=RecruiterDashboardResponse)
def get_recruiter_dashboard(
    current_user: User = Depends(require_role(["recruiter", "admin"])),
    db: Session = Depends(get_db)
):
    """Retrieve hiring pipeline analytics and applicants for recruiter dashboard."""
    return DashboardService.get_recruiter_dashboard(db, current_user)


@router.get("/admin", response_model=AdminDashboardResponse)
def get_admin_dashboard(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Retrieve platform-wide statistics, health status, and fairness summaries."""
    return DashboardService.get_admin_dashboard(db)
