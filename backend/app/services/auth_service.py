from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password
)
from app.models.models import CandidateProfile, Company, RecruiterProfile, User
from app.schemas.schemas import UserRegister


class AuthService:
    @staticmethod
    def register_user(db: Session, data: UserRegister) -> User:
        # Administrator accounts cannot be self-registered through the public API.
        if data.role == "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrator accounts cannot be created through public registration."
            )
        existing = db.query(User).filter(User.email == data.email.lower()).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists."
            )

        new_user = User(
            email=data.email.lower(),
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            role=data.role,
            is_active=True,
            is_verified=True
        )
        db.add(new_user)
        db.flush()

        # Create corresponding profile
        if data.role == "candidate":
            profile = CandidateProfile(
                user_id=new_user.id,
                target_title="Software Professional",
                profile_completion=30.0
            )
            db.add(profile)
        elif data.role == "recruiter":
            company = None
            if data.company_name:
                company = db.query(Company).filter(Company.name == data.company_name).first()
                if not company:
                    company = Company(name=data.company_name)
                    db.add(company)
                    db.flush()
            rec_profile = RecruiterProfile(
                user_id=new_user.id,
                company_id=company.id if company else None,
                title="Talent Acquisition Partner"
            )
            db.add(rec_profile)

        db.commit()
        db.refresh(new_user)
        return new_user

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User:
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This user account has been deactivated."
            )
        return user

    @staticmethod
    def generate_tokens(user: User):
        access_token = create_access_token(subject=user.id, role=user.role)
        refresh_token = create_refresh_token(subject=user.id, role=user.role)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role
            }
        }

    @staticmethod
    def refresh_access_token(db: Session, refresh_token_str: str):
        try:
            payload = decode_token(refresh_token_str)
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=400, detail="Invalid token type.")
            user_id = payload.get("sub")
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="User not found or inactive.")
            return AuthService.generate_tokens(user)
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Token refresh failed: {str(e)}")
