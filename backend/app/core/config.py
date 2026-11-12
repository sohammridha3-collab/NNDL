import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==============================================================================
# Canonical Directory Anchors
# Resolves paths deterministically regardless of execution working directory.
# ==============================================================================
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Check for .env file in order of priority: PROJECT_ROOT, then BACKEND_DIR
_env_file_candidates = [
    PROJECT_ROOT / ".env",
    BACKEND_DIR / ".env"
]
ENV_FILE_PATH = next((p for p in _env_file_candidates if p.exists()), PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    PROJECT_NAME: str = "Inclusive Resume and Job Matching System"
    PROJECT_DESCRIPTION: str = (
        "AI-Powered ATS Platform for Inclusive Candidate & Job Matching - SDG 10: Reduced Inequalities"
    )
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Base directory paths
    ROOT_DIR: Path = PROJECT_ROOT
    APP_DIR: Path = BACKEND_DIR
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "inclusive-ats-super-secret-jwt-key-2026-production-ready")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Database Configuration
    # Defaults explicitly to the verified project SQLite database; no silent fallback switching.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(PROJECT_ROOT / 'inclusive_ats.db').as_posix()}"
    )
    
    # CORS Configuration
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001,https://inclusive-ats-frontend.onrender.com"
    )
    
    # ML Model Configuration - explicitly anchored to backend/app/ml/artifacts/model.pkl
    MODEL_PATH: str = os.getenv("MODEL_PATH", str(BACKEND_DIR / "app" / "ml" / "artifacts" / "model.pkl"))
    ENCODER_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    DEVICE: str = os.getenv("DEVICE", "cpu")
    
    # File Storage Configuration - explicitly anchored to project root uploads/
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "uploads"))
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
    
    # SDG 10 Bias Masking Setting
    ENABLE_BIAS_MASKING: bool = True

    # External Job API Configuration (Adzuna / Remotive)
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")
    ADZUNA_COUNTRY: str = os.getenv("ADZUNA_COUNTRY", "us")
    ENABLE_EXTERNAL_JOBS: bool = os.getenv("ENABLE_EXTERNAL_JOBS", "true").lower() in ("true", "1", "yes")

    @property
    def cors_origins(self) -> List[str]:
        origins = [
            origin.strip().rstrip("/")
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]
        return origins

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        extra="allow",
        env_file_encoding="utf-8"
    )


settings = Settings()
