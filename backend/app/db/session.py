import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

logger = logging.getLogger("inclusive_ats.db")

Base = declarative_base()


def create_database_engine():
    target_url = settings.DATABASE_URL
    is_sqlite = target_url.startswith("sqlite")
    
    # Try the configured database (MySQL / PostgreSQL / SQLite)
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
                connect_args={"connect_timeout": 3}
            )
        # Test connection
        with engine.connect() as conn:
            pass
        logger.info(f"Database connected successfully to: {target_url.split('@')[-1] if '@' in target_url else 'SQLite'}")
        return engine
    except Exception as e:
        logger.warning(
            f"Could not connect to configured database at '{target_url}'. "
            f"Error: {e}. Falling back to SQLite local database: {settings.FALLBACK_SQLITE_URL}"
        )
        return create_engine(
            settings.FALLBACK_SQLITE_URL,
            connect_args={"check_same_thread": False}
        )


engine = create_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
