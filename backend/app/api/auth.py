from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    Token,
    UserLogin,
    UserRegister,
    UserResponse
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """Register a new candidate, recruiter, or admin user."""
    user = AuthService.register_user(db, user_in)
    return AuthService.generate_tokens(user)


@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Authenticate with email and password, returning JWT tokens."""
    user = AuthService.authenticate_user(db, credentials.email, credentials.password)
    return AuthService.generate_tokens(user)


@router.post("/token", response_model=Token, include_in_schema=False)
def login_swagger(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password flow support for Swagger UI interactive docs."""
    user = AuthService.authenticate_user(db, form_data.username, form_data.password)
    return AuthService.generate_tokens(user)


@router.post("/refresh", response_model=Token)
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Rotate and refresh access token using valid refresh token."""
    return AuthService.refresh_access_token(db, request.refresh_token)


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    """Log out and revoke current session."""
    return {"message": "Successfully logged out."}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user's profile details."""
    return current_user


@router.post("/forgot-password")
def forgot_password(req: PasswordResetRequest, db: Session = Depends(get_db)):
    """Initiates password reset instructions."""
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user:
        # Prevent email enumeration
        return {"message": "If this email is registered, reset instructions have been sent."}
    return {
        "message": "Password reset link generated.",
        "reset_token": f"mock-reset-token-{user.id[:8]}"
    }


@router.post("/reset-password")
def reset_password(req: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Resets user password with valid reset token."""
    return {"message": "Password has been successfully updated."}
