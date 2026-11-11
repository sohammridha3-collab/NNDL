from typing import Any, Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import FairnessAudit, User
from app.schemas.schemas import FairnessAuditRequest, FairnessAuditResponse
from app.services.fairness_service import FairnessService

router = APIRouter(prefix="/fairness", tags=["Fairness & SDG 10"])


@router.post("/audit", response_model=FairnessAuditResponse)
def run_fairness_audit(
    request: FairnessAuditRequest,
    current_user: User = Depends(require_role(["admin", "recruiter"])),
    db: Session = Depends(get_db)
):
    """
    Execute real counterfactual fairness testing across demographic variations
    under SDG 10: Reduced Inequalities.
    Tests model score invariance with and without personal detail masking.
    """
    return FairnessService.run_sdg10_fairness_audit(db, audit_name=request.name or "SDG 10 Counterfactual Fairness Audit")


@router.get("/reports")
def get_fairness_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """View historical fairness audit reports and demographic invariance metrics."""
    reports = FairnessService.get_fairness_reports(db)
    return [
        {
            "id": r.id,
            "name": r.name,
            "audit_type": r.audit_type,
            "total_pairs": r.total_pairs,
            "metrics": r.metrics,
            "model_version": r.model_version,
            "created_at": r.created_at
        }
        for r in reports
    ]
