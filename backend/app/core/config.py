import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Inclusive Resume and Job Matching System"
    PROJECT_DESCRIPTION: str = (
        "AI-Powered ATS Platform for Inclusive Candidate & Job Matching - SDG 10: Reduced Inequalities"
    )
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "inclusive-ats-super-secret-jwt-key-2026-production-ready")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Database Configuration (MySQL default with automatic SQLite fallback)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/inclusive_ats"
    )
    FALLBACK_SQLITE_URL: str = "sqlite:///./inclusive_ats.db"
    
    # CORS Configuration
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001"
    )
    
    # ML Model Configuration
    MODEL_PATH: str = os.getenv("MODEL_PATH", "app/ml/artifacts/model.pkl")
    ENCODER_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    DEVICE: str = os.getenv("DEVICE", "cpu")
    
    # File Storage Configuration
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    
    # SDG 10 Bias Masking Setting
    ENABLE_BIAS_MASKING: bool = True

    @property
    def cors_origins(self) -> List[str]:
        origins = [
            origin.strip().rstrip("/")
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]
        return origins

    model_config = SettingsConfigDict(env_file=".env", extra="allow")


settings = Settings()
