import io


def test_cors_preflight_headers(client):
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type"
    }
    response = client.options("/api/v1/auth/login", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "POST" in response.headers.get("access-control-allow-methods", "")


def test_health_and_readiness(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    ready = client.get("/ready?wait=60")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["ml_model"] == "loaded"


def test_end_to_end_recruitment_lifecycle(client):
    """
    End-to-End Test:
    1. Recruiter registers & posts a Job
    2. Candidate registers
    3. Candidate uploads resume
    4. Candidate receives ATS analysis
    5. Candidate views recommended jobs
    6. Candidate matches with job (AI prediction)
    7. Candidate applies for job
    8. Recruiter logs in, reviews ranked applicants, and shortlists candidate
    """
    # 1. Recruiter registers & creates job
    rec_reg = client.post("/api/v1/auth/register", json={
        "email": "lead_recruiter@enterprise.com",
        "password": "Password123!",
        "full_name": "Clara Oswald",
        "role": "recruiter",
        "company_name": "Enterprise Solutions"
    })
    assert rec_reg.status_code == 201
    rec_token = rec_reg.json()["access_token"]
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    job_create = client.post("/api/v1/jobs", headers=rec_headers, json={
        "title": "Senior AI Systems Engineer",
        "category": "Artificial Intelligence",
        "description": "Looking for Senior AI Engineer skilled in Python, PyTorch, Docker, SQL, and Machine Learning.",
        "skills": ["python", "pytorch", "docker", "sql", "machine learning"]
    })
    assert job_create.status_code == 201
    job_id = job_create.json()["id"]

    # 2. Candidate registers
    cand_reg = client.post("/api/v1/auth/register", json={
        "email": "ai_candidate@university.edu",
        "password": "Password123!",
        "full_name": "Rory Williams",
        "role": "candidate"
    })
    assert cand_reg.status_code == 201
    cand_token = cand_reg.json()["access_token"]
    cand_headers = {"Authorization": f"Bearer {cand_token}"}

    # 3. Candidate uploads resume
    resume_text = b"""
    Summary: Experienced AI Engineer specializing in deep learning and NLP architectures.
    Skills: Python, PyTorch, Docker, SQL, Machine Learning, Git.
    Experience: 4 years training transformer pipelines and deploying real-time APIs.
    Education: Master of Science in Computer Science.
    """
    upload_res = client.post("/api/v1/resumes/upload", headers=cand_headers, files={
        "file": ("ai_engineer_resume.txt", io.BytesIO(resume_text), "text/plain")
    })
    assert upload_res.status_code == 201
    resume_id = upload_res.json()["id"]

    # 4. Candidate receives ATS analysis
    analysis_res = client.post(f"/api/v1/resumes/{resume_id}/analyze", headers=cand_headers)
    assert analysis_res.status_code == 200
    assert analysis_res.json()["ats_score"] > 60.0

    # 5. Candidate views recommended jobs
    rec_jobs_res = client.get("/api/v1/recommendations/jobs?limit=5", headers=cand_headers)
    assert rec_jobs_res.status_code == 200
    assert len(rec_jobs_res.json()["recommendations"]) >= 1

    # 6. Candidate runs AI matching against job
    match_res = client.post("/api/v1/matching/predict", headers=cand_headers, json={
        "resume_id": resume_id,
        "job_id": job_id
    })
    assert match_res.status_code == 200
    match_data = match_res.json()
    assert match_data["compatibility_score"] >= 0.0
    assert "python" in [s.lower() for s in match_data["matched_skills"]]

    # 7. Candidate applies for job
    apply_res = client.post(f"/api/v1/jobs/{job_id}/apply", headers=cand_headers, json={
        "resume_id": resume_id,
        "cover_note": "Thrilled to apply for the Senior AI role."
    })
    assert apply_res.status_code == 201
    app_id = apply_res.json()["id"]

    # 8. Recruiter reviews application & moves stage to shortlisted
    applicants_res = client.get(f"/api/v1/jobs/{job_id}/applicants", headers=rec_headers)
    assert applicants_res.status_code == 200
    applicants = applicants_res.json()
    assert len(applicants) == 1
    assert applicants[0]["id"] == app_id

    stage_res = client.put(f"/api/v1/jobs/{job_id}/applicants/{app_id}", headers=rec_headers, json={
        "status": "shortlisted",
        "stage": "Interview",
        "recruiter_note": "Excellent resume match; schedule screening."
    })
    assert stage_res.status_code == 200
    assert stage_res.json()["status"] == "shortlisted"
    assert stage_res.json()["stage"] == "Interview"
