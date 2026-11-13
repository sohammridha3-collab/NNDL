import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings, redact_sensitive_url

logger = logging.getLogger("inclusive_ats.db")

Base = declarative_base()


def create_database_engine():
    target_url = settings.DATABASE_URL
    is_sqlite = target_url.startswith("sqlite")
    
    try:
        if is_sqlite:
            engine = create_engine(
                target_url,
                connect_args={"check_same_thread": False}
            )
        else:
            engine = create_engine(
                target_url,
                pool_pre_ping=True,
                pool_recycle=3600,
                pool_size=10,
                max_overflow=20,
                connect_args={"connect_timeout": 5}
            )
        # Verify connection immediately
        with engine.connect() as conn:
            pass
        safe_url = redact_sensitive_url(target_url)
        db_label = safe_url.split("@")[-1] if "@" in safe_url else "SQLite Database"
        logger.info(f"Database connected successfully: {db_label}")
        return engine
    except Exception as e:
        safe_url = redact_sensitive_url(target_url)
        logger.error(
            f"CRITICAL: Failed to connect to configured DATABASE_URL: '{safe_url}'. Error: {e}",
            exc_info=True
        )
        # Fail clearly with actionable guidance instead of silent database switching
        raise RuntimeError(
            f"Database Connection Failure: Could not establish a connection to '{safe_url}'. "
            f"Underlying error: {e}. "
            "Please check that your database server is running and credentials are valid. "
            "For local development, ensure DATABASE_URL is set to a valid SQLite database path."
        ) from e


engine = create_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
