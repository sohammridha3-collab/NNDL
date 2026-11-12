import sys
from pathlib import Path

# Ensure the backend directory is in sys.path when running main.py directly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import threading
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, auth, dashboard, fairness, jobs, matching, recommendations, resumes
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import Base, engine
from app.ml.inference import MLInferenceService

setup_logging()
logger = logging.getLogger("inclusive_ats.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database Tables
    logger.info("Initializing database schema...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified/created successfully.")
    except Exception as e:
        logger.error(f"Database schema initialization error: {e}", exc_info=True)

    # Startup: Trigger background non-blocking ML model pre-warming
    logger.info("Triggering non-blocking ML inference engine warm-up...")
    MLInferenceService.warmup_async()

    yield

    # Shutdown
    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Cross-Origin Resource Sharing (CORS) Configuration
origins = settings.cors_origins
logger.info(f"Configuring CORS with allowed origins: {origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["*"]
)


# Global Exception Handler for clean error messages
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error processing {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."}
    )


# Health & Readiness Probes
@app.get("/health", tags=["System"])
def health_check():
    """Liveness probe: verifies service is running."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }


@app.get("/ready", tags=["System"])
def readiness_check():
    """Readiness probe: checks database connection and ML model state."""
    db_ok = False
    db_msg = "unreachable"
    try:
        with engine.connect() as conn:
            db_ok = True
            db_msg = "connected"
    except Exception as e:
        db_msg = f"error: {str(e)}"

    if not MLInferenceService.is_ready():
        # Allow background warmup up to 10s to complete
        MLInferenceService._ready_event.wait(timeout=10.0)

    ml_status = MLInferenceService.status_dict()
    all_ready = db_ok and ml_status.get("is_ready", False)

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "ready": all_ready,
            "database": db_msg,
            "ml_model": "loaded" if all_ready else ml_status.get("state", "unknown"),
            "model_state": ml_status.get("state", "unknown"),
            "model_type": ml_status.get("model_type"),
            "threshold": ml_status.get("threshold"),
            "model_error": ml_status.get("error")
        }
    )


@app.get("/", tags=["System"])
def root_endpoint():
    """Root metadata endpoint."""
    return {
        "name": settings.PROJECT_NAME,
        "description": settings.PROJECT_DESCRIPTION,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
        "sdg_target": "SDG 10: Reduced Inequalities"
    }


# Register Versioned API Routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(resumes.router, prefix=settings.API_V1_STR)
app.include_router(jobs.router, prefix=settings.API_V1_STR)
app.include_router(matching.router, prefix=settings.API_V1_STR)
app.include_router(recommendations.router, prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(fairness.router, prefix=settings.API_V1_STR)
app.include_router(admin.router, prefix=settings.API_V1_STR)


if __name__ == "__main__":
    import os
    import uvicorn

    host = "127.0.0.1"
    port = int(os.getenv("PORT", "8001"))

    print("\n" + "=" * 70)
    print(" >>> Inclusive Resume & Job Matching API is starting up... <<<")
    print(f" -> Local Web Service:      http://{host}:{port}")
    print(f" -> Interactive Swagger UI: http://{host}:{port}/docs")
    print(f" -> Alternative Redoc UI:   http://{host}:{port}/redoc")
    print(f" -> Health Check Endpoint:  http://{host}:{port}/health")
    print(f" -> Frontend App:           http://{host}:5500/frontend/")
    print("=" * 70 + "\n")
    uvicorn.run("app.main:app", host=host, port=port, reload=False, app_dir=str(backend_dir))
