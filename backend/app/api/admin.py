import platform
import sys
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.models import Job, SecurityAuditLog, User
from app.schemas.schemas import UserResponse

router = APIRouter(prefix="/admin", tags=["Admin Management"])


@router.get("/users", response_model=List[UserResponse])
def list_all_users(
    role: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Admin: List all registered platform users."""
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return users


@router.put("/users/{user_id}/status")
def toggle_user_status(
    user_id: str,
    is_active: bool,
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Admin: Activate or deactivate a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == current_user.id and not is_active:
        raise HTTPException(status_code=400, detail="Administrators cannot deactivate their own account.")
    user.is_active = is_active
    db.commit()
    return {"message": f"User '{user.email}' status updated to active={is_active}.", "is_active": is_active}


@router.get("/audit-logs")
def get_audit_logs(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Admin: View system security audit logs."""
    logs = db.query(SecurityAuditLog).order_by(SecurityAuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "details": log.details,
            "created_at": log.created_at,
        }
        for log in logs
    ]


@router.get("/system-health")
def get_detailed_system_health(
    current_user: User = Depends(require_role(["admin"])),
    db: Session = Depends(get_db)
):
    """Admin: Monitor server environment, ML model status, and database connectivity."""
    from app.ml.inference import MLInferenceService
    from sqlalchemy import text as sql_text
    try:
        service = MLInferenceService.get_instance()
        ml_status = {
            "model_loaded": True,
            "model_type": service.model_type,
            "architecture": service.architecture,
            "threshold": service.threshold,
            "label_mapping": {str(k): v for k, v in (service.label_mapping or {}).items()},
            "device": service.device,
            "encoder": service.encoder.model_name
        }
    except Exception as e:
        ml_status = {"model_loaded": False, "error": str(e)}

    try:
        db.execute(sql_text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "platform": platform.platform(),
        "python_version": sys.version,
        "database_connected": db_ok,
        "ml_service": ml_status
    }
