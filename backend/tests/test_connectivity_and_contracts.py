import os
from pathlib import Path
from unittest.mock import patch
import pytest
from pydantic import ValidationError

from app.core.config import Settings, PROJECT_ROOT, BACKEND_DIR
from app.schemas.schemas import UserRegister, JobRecommendationItem, SkillRecommendationRequest
from app.services.recommendation_service import RecommendationService
from app.models.models import Job, User, Company
from app.db.session import engine


def test_pydantic_email_validation():
    """Verify that email validation functions properly via pydantic[email] and email-validator."""
    # Valid email succeeds
    valid_user = UserRegister(
        email="test.engineer@example.com",
        password="SecurePassword123!",
        full_name="Valid Candidate",
        role="candidate"
    )
    assert valid_user.email == "test.engineer@example.com"

    # Malformed email raises validation error
    with pytest.raises(ValidationError):
        UserRegister(
            email="not-an-email",
            password="SecurePassword123!",
            full_name="Invalid Candidate",
            role="candidate"
        )


def test_path_normalization_consistency():
    """Verify that relative paths in settings resolve deterministically against anchors."""
    # Test with relative SQLite path
    settings_rel = Settings(
        DATABASE_URL="sqlite:///./test_rel.db",
        MODEL_PATH="app/ml/artifacts/model.pkl",
        UPLOAD_DIR="uploads"
    )
    # Database path must resolve to PROJECT_ROOT / test_rel.db
    expected_db_suffix = (PROJECT_ROOT / "test_rel.db").as_posix()
    assert expected_db_suffix in settings_rel.DATABASE_URL
    assert not settings_rel.DATABASE_URL.startswith("sqlite:///./")

    # Model path must resolve to BACKEND_DIR / app/ml/artifacts/model.pkl
    expected_model = str((BACKEND_DIR / "app" / "ml" / "artifacts" / "model.pkl").resolve())
    assert Path(settings_rel.MODEL_PATH).resolve() == Path(expected_model)

    # Upload dir must resolve to PROJECT_ROOT / uploads
    expected_upload = str((PROJECT_ROOT / "uploads").resolve())
    assert Path(settings_rel.UPLOAD_DIR).resolve() == Path(expected_upload)


def test_isolated_test_database():
    """Verify that the test suite runs on an isolated test database and not the live user database."""
    current_db_url = str(engine.url)
    assert "test_isolated.db" in current_db_url
    assert "inclusive_ats.db" not in current_db_url or "test_isolated.db" in current_db_url
    # Ensure real database files exist and are intact
    real_db_root = PROJECT_ROOT / "inclusive_ats.db"
    assert real_db_root.exists()


def test_cors_headers_on_error(client):
    """Verify CORS headers are returned properly for allowed origins even on unhandled errors."""
    from starlette.testclient import TestClient
    from app.main import app

    allowed_origin = "http://127.0.0.1:5500"
    no_raise_client = TestClient(app, raise_server_exceptions=False)

    # Preflight OPTIONS
    res_options = no_raise_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization"
        }
    )
    assert res_options.status_code == 200
    assert res_options.headers.get("access-control-allow-origin") == allowed_origin

    # Trigger unhandled error to verify global_exception_handler injects CORS headers
    with patch("app.services.auth_service.AuthService.authenticate_user", side_effect=RuntimeError("Simulated unhandled internal crash")):
        res_error = no_raise_client.post(
            "/api/v1/auth/login",
            json={"email": "crash@test.com", "password": "Password123!"},
            headers={"Origin": allowed_origin}
        )
        assert res_error.status_code == 500
        assert res_error.headers.get("access-control-allow-origin") == allowed_origin
        assert res_error.headers.get("access-control-allow-credentials") == "true"


def test_model_unavailable_decoupling(db):
    """Verify recommendation service returns unranked listings without failing when model is unavailable."""
    # Create sample company & job in database
    company = Company(name="Tech Innovations")
    db.add(company)
    db.commit()
    db.refresh(company)

    job = Job(
        title="Full Stack Software Engineer",
        company_id=company.id,
        location="Kolkata",
        job_type="hybrid",
        description="We need a Full Stack Developer experienced in Python, React, and PostgreSQL.",
        requirements="Python, React, SQL",
        status="active"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Force MLInferenceService to appear uninitialized or unavailable
    with patch("app.ml.inference.MLInferenceService.is_ready", return_value=False), \
         patch("app.ml.inference.MLInferenceService.get_instance", side_effect=RuntimeError("Model offline")):
        
        req = SkillRecommendationRequest(
            skills=["python", "react"],
            location="Kolkata",
            limit=5,
            include_external=False
        )
        
        # Must succeed and return the vacancy
        response = RecommendationService.recommend_jobs_by_skills(db, req, current_user=None)
        assert response.total >= 1
        item = response.items[0]
        assert item.title == "Full Stack Software Engineer"
        # Must be marked unranked without fabricated fake probabilities
        assert item.score is None
        assert "unranked" in item.score_type.lower() or item.score_label == "Unranked (Scoring Unavailable)"
        # Consumer aliases must be populated
        assert item.job_id == item.id
        assert item.compatibility_score is None
        assert item.recommendation_reason is not None


def test_dashboard_recommendation_contract(client):
    """Verify /recommendations/jobs contract delivers consumer-compatible fields for dashboard.js."""
    # Register candidate
    res = client.post("/api/v1/auth/register", json={
        "email": "contract_tester@example.com",
        "password": "Password123!",
        "full_name": "Contract Tester",
        "role": "candidate"
    })
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Query recommendations
    recs_res = client.get("/api/v1/recommendations/jobs?limit=5", headers=headers)
    assert recs_res.status_code == 200
    data = recs_res.json()
    assert "recommendations" in data
    for item in data["recommendations"]:
        # Verify required dashboard.js contract keys
        assert "job_id" in item
        assert "compatibility_score" in item
        assert "recommendation_reason" in item
        assert "title" in item
        assert "company_name" in item
        assert "location" in item


def test_cors_preflight_production_render_origin(client):
    """Verify CORS preflight succeeds for deployed frontend on Render."""
    prod_origin = "https://inclusive-ats-frontend.onrender.com"
    res = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": prod_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization"
        }
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == prod_origin
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_extract_skills_graceful_without_model(db):
    """Verify skill extraction functions cleanly using fallback vocabulary when model is offline."""
    from app.schemas.schemas import SkillExtractionRequest
    with patch("app.ml.inference.MLInferenceService.is_ready", return_value=False), \
         patch("app.ml.inference.MLInferenceService.get_instance", side_effect=RuntimeError("Model offline")):
        
        req = SkillExtractionRequest(
            text="Experienced software engineer proficient in Python, React, Docker, and PostgreSQL."
        )
        res = RecommendationService.extract_skills_from_input(db, req)
        assert res.count >= 2
        assert "python" in [s.lower() for s in res.skills]


def test_app_main_lazy_ml_import():
    """Importing app.main must not eagerly import torch or sentence_transformers so port 8001 binds fast."""
    import subprocess
    import sys

    code = (
        f"import sys; sys.path.insert(0, {str(BACKEND_DIR)!r}); "
        "import app.main; "
        "assert 'sentence_transformers' not in sys.modules, 'sentence_transformers imported eagerly'; "
        "assert 'torch' not in sys.modules, 'torch imported eagerly'; "
        "print('LAZY_IMPORT_OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "LAZY_IMPORT_OK" in proc.stdout


def test_endpoints_available_while_model_loading(client, db):
    """Auth, dashboard, /health, /openapi.json, and job retrieval remain available during ML loading; /ready & ML matching return 503."""
    from fastapi import HTTPException
    from app.ml.inference import MLInferenceService, ModelState

    # Register & verify auth works while ML is warming up
    reg = client.post("/api/v1/auth/register", json={
        "email": "loading_state_tester@example.com",
        "password": "Password123!",
        "full_name": "Loading State Tester",
        "role": "candidate",
    })
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    loading_status = {
        "state": "loading",
        "is_ready": False,
        "error": None,
        "model_type": None,
        "threshold": None,
    }
    loading_exc = HTTPException(
        status_code=503,
        detail="ML Inference Engine is currently warming up. Please retry in a few seconds.",
        headers={"Retry-After": "5"},
    )

    with patch.object(MLInferenceService, "is_ready", return_value=False), \
         patch.object(MLInferenceService, "status_dict", return_value=loading_status), \
         patch.object(MLInferenceService, "get_instance", side_effect=loading_exc):
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200

        ready = client.get("/ready?wait=0")
        assert ready.status_code == 503
        ready_json = ready.json()
        assert ready_json["ready"] is False
        assert ready_json["model_state"] == "loading"
        assert "warming up" in ready_json["detail"].lower()

        dash = client.get("/api/v1/dashboard/candidate", headers=headers)
        assert dash.status_code == 200

        recs = client.get("/api/v1/recommendations/jobs?limit=3", headers=headers)
        assert recs.status_code == 200
        assert "recommendations" in recs.json()

        match_res = client.post(
            "/api/v1/matching/predict",
            headers=headers,
            json={
                "resume_text": "Experienced Python FastAPI backend developer with PostgreSQL and Docker skills.",
                "job_text": "Seeking a Python FastAPI engineer experienced with SQL databases and containers.",
            },
        )
        assert match_res.status_code == 503
        assert "warming up" in match_res.json()["detail"].lower()



