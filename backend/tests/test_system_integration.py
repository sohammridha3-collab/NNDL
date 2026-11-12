import os
import sys
import socket
import pytest
from fastapi.testclient import TestClient

# Add project root and backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.ml.inference import MLInferenceService, ModelState
from app.ml.preprocessing import extract_requirements_breakdown, generate_learning_checklist
from app.db.session import create_database_engine
from main import check_port_availability


def test_port_conflict_detection_without_taskkill():
    """Verify port availability checker detects occupied ports non-destructively."""
    temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    temp_sock.bind(("127.0.0.1", 0))
    port = temp_sock.getsockname()[1]
    
    # While temp_sock is bound, check_port_availability should report False
    assert check_port_availability("127.0.0.1", port) is False
    
    # After releasing, it should report True
    temp_sock.close()
    assert check_port_availability("127.0.0.1", port) is True


def test_database_no_silent_fallback(monkeypatch):
    """Verify DB engine throws descriptive RuntimeError on connection error rather than silently switching."""
    from app.core import config
    
    monkeypatch.setattr(config.settings, "DATABASE_URL", "mysql+pymysql://invalid_user:invalid_pass@127.0.0.1:9999/nonexistent_db")
    
    with pytest.raises(RuntimeError) as exc_info:
        create_database_engine()
    
    assert "Database Connection Failure" in str(exc_info.value)


def test_model_lifecycle_and_thread_safety():
    """Verify model service lifecycle states and thread-safe instance retrieval."""
    svc = MLInferenceService.get_instance(wait_timeout=5.0)
    assert svc is not None
    assert svc.is_ready()
    status = svc.status_dict()
    assert status["state"] == ModelState.READY.value
    assert status["feature_dimension"] == 770
    assert status["threshold"] > 0.0


def test_requirements_breakdown_and_checklist():
    """Verify essential vs preferred extraction and learning project suggestions."""
    job_desc = (
        "Requirements:\n"
        "Must have 3+ years experience with Python and FastAPI.\n"
        "Required: Strong understanding of Docker and PostgreSQL.\n"
        "Nice to have: Experience with Kubernetes, GraphQL, and AWS."
    )
    breakdown = extract_requirements_breakdown(job_desc)
    assert "essential_skills" in breakdown
    assert "preferred_skills" in breakdown
    assert len(breakdown["essential_skills"]) > 0
    assert any("python" in s.lower() or "fastapi" in s.lower() for s in breakdown["essential_skills"])

    missing_skills = ["Kubernetes", "GraphQL"]
    checklist = generate_learning_checklist(missing_skills)
    assert len(checklist) == 2
    for item in checklist:
        assert "skill" in item
        assert "practice_project" in item
        assert "guidance" in item


def test_full_inference_output_schema():
    """Verify 770-dim feature vector inference returns complete enriched schema and dataset disclaimer."""
    svc = MLInferenceService.get_instance()
    resume_text = (
        "Senior Software Engineer with 5 years experience in Python, FastAPI, Docker, and PostgreSQL. "
        "Built REST APIs, deployed microservices, and optimized relational database queries."
    )
    job_text = (
        "We are looking for a Python Backend Developer skilled in Python, FastAPI, and PostgreSQL. "
        "Experience with Docker and CI/CD pipelines preferred."
    )
    result = svc.predict_pair(resume_text, job_text)
    
    assert "compatibility_score" in result
    assert "raw_probability" in result
    assert "decision_threshold" in result
    assert "classification" in result
    assert "semantic_similarity" in result
    assert "required_skill_coverage" in result
    assert "matched_skills" in result
    assert "missing_skills" in result
    assert "requirements_breakdown" in result
    assert "learning_checklist" in result
    assert "disclaimer" in result
    
    # 0-100 range validation
    assert 0.0 <= result["compatibility_score"] <= 100.0
    assert 0.0 <= result["raw_probability"] <= 1.0
    assert 0.0 <= result["semantic_similarity"] <= 1.0
    assert 0.0 <= result["required_skill_coverage"] <= 1.0
    
    # Disclaimer text verification
    assert "dataset" in result["disclaimer"].lower() or "training" in result["disclaimer"].lower()
    assert "hired" in result["disclaimer"].lower()


def test_extract_skills_endpoint(client):
    """Verify POST /api/v1/recommendations/extract-skills returns parsed skill tags."""
    payload = {
        "resume_text": "Proficient in Python, React, TypeScript, Docker, and AWS."
    }
    response = client.post("/api/v1/recommendations/extract-skills", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "skills" in data
    assert isinstance(data["skills"], list)
    assert "python" in [s.lower() for s in data["skills"]]
    assert "react" in [s.lower() for s in data["skills"]]


def test_skill_recommendations_endpoint(client, test_recruiter, recruiter_token):
    """Verify POST /api/v1/recommendations/skills calculates skills-only relevance."""
    # Seed a job using recruiter
    job_payload = {
        "title": "Cloud Python Engineer",
        "category": "Software & Technology",
        "description": "Seeking a talented Python and Docker engineer to maintain services.",
        "requirements": "3+ years Python experience required.",
        "location": "Remote",
        "job_type": "remote",
        "experience_level": "Mid-Level",
        "skills": ["python", "docker", "sql"]
    }
    create_resp = client.post(
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {recruiter_token}"},
        json=job_payload
    )
    assert create_resp.status_code == 201

    payload = {
        "skills": ["Python", "Docker"],
        "job_type": "remote",
        "include_external": False
    }
    response = client.post("/api/v1/recommendations/skills", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    first_item = data["items"][0]
    assert first_item["score_type"] == "skills_only_relevance"
    assert "matched_skills" in first_item
    assert "missing_skills" in first_item


def test_save_external_job_endpoint(client, test_candidate, candidate_token):
    """Verify authenticated candidate can persist an external job listing."""
    headers = {"Authorization": f"Bearer {candidate_token}"}
    
    payload = {
        "title": "Staff Backend Engineer",
        "company_name": "CloudScale Inc",
        "location": "Remote",
        "description": "Building distributed systems in Go and Python with high concurrency.",
        "skills": ["Go", "Python", "Kubernetes"],
        "work_arrangement": "remote",
        "external_id": "ext-test-12345",
        "external_url": "https://example.com/jobs/12345",
        "source": "Remotive"
    }
    
    response = client.post("/api/v1/jobs/save-external", json=payload, headers=headers)
    assert response.status_code == 201
    saved_data = response.json()
    assert saved_data["title"] == "Staff Backend Engineer"
    assert saved_data["is_external"] is True
    assert saved_data["external_url"] == "https://example.com/jobs/12345"
