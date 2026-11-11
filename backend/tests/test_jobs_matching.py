import io


def test_job_crud_and_permissions(client, test_recruiter, recruiter_token, test_candidate, candidate_token):
    # Recruiter creates job
    rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
    job_payload = {
        "title": "Lead Python ML Architect",
        "category": "Artificial Intelligence",
        "description": "Seeking an expert in Python, PyTorch, SQL, Docker, and AWS to architect inclusive ATS matching systems.",
        "requirements": "5+ years with Python and deep learning frameworks.",
        "location": "Remote",
        "job_type": "remote",
        "experience_level": "Senior",
        "min_salary": 140000,
        "max_salary": 180000,
        "skills": ["python", "pytorch", "docker", "sql", "aws"]
    }
    create_resp = client.post("/api/v1/jobs", headers=rec_headers, json=job_payload)
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    # Candidate denied creating job
    cand_headers = {"Authorization": f"Bearer {candidate_token}"}
    denied_resp = client.post("/api/v1/jobs", headers=cand_headers, json=job_payload)
    assert denied_resp.status_code == 403

    # Public job listing and filtering
    list_resp = client.get("/api/v1/jobs?q=Python")
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert len(jobs) >= 1
    assert any(j["id"] == job_id for j in jobs)


def test_matching_predict_and_explanation(client, test_candidate, candidate_token):
    headers = {"Authorization": f"Bearer {candidate_token}"}
    match_payload = {
        "resume_text": "Experienced Python Engineer. Proficient in SQL, Docker, and Machine Learning with 5 years building scalable web services.",
        "job_text": "Senior Software Engineer. Must have strong Python, Docker, SQL, and Machine Learning background."
    }
    resp = client.post("/api/v1/matching/predict", headers=headers, json=match_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "compatibility_score" in data
    assert "classification" in data
    assert "semantic_similarity" in data
    assert "matched_skills" in data
    assert "missing_skills" in data
    assert "recommendations" in data
    assert "explanation" in data


def test_candidate_apply_and_recruiter_review(client, test_candidate, candidate_token, test_recruiter, recruiter_token):
    # 1. Recruiter creates job
    rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
    job_resp = client.post("/api/v1/jobs", headers=rec_headers, json={
        "title": "Backend Systems Engineer",
        "category": "Backend Engineering",
        "description": "Looking for Backend Engineer with Python, SQL, Git, and Linux experience.",
        "skills": ["python", "sql", "git", "linux"]
    })
    job_id = job_resp.json()["id"]

    # 2. Candidate uploads resume
    cand_headers = {"Authorization": f"Bearer {candidate_token}"}
    resume_content = b"""
    Summary: Backend developer passionate about clean architecture.
    Skills: Python, SQL, Git, Linux, Docker.
    Experience: 4 years designing REST APIs and distributed data models.
    Education: B.S. in Computer Engineering.
    """
    files = {"file": ("backend_dev.txt", io.BytesIO(resume_content), "text/plain")}
    res_resp = client.post("/api/v1/resumes/upload", headers=cand_headers, files=files)
    assert res_resp.status_code == 201

    # 3. Candidate applies
    apply_resp = client.post(f"/api/v1/jobs/{job_id}/apply", headers=cand_headers, json={
        "cover_note": "I would love to contribute to this team!"
    })
    assert apply_resp.status_code == 201
    app_data = apply_resp.json()
    assert app_data["job_id"] == job_id
    assert app_data["candidate_id"] == test_candidate.id
    assert app_data["status"] == "applied"
    assert app_data["match_score"] is not None

    # 4. Recruiter reviews applicants (sorted by AI score)
    applicants_resp = client.get(f"/api/v1/jobs/{job_id}/applicants", headers=rec_headers)
    assert applicants_resp.status_code == 200
    apps = applicants_resp.json()
    assert len(apps) >= 1
    target_app = apps[0]
    assert target_app["candidate_id"] == test_candidate.id

    # 5. Recruiter updates candidate stage
    app_id = target_app["id"]
    stage_resp = client.put(f"/api/v1/jobs/{job_id}/applicants/{app_id}", headers=rec_headers, json={
        "status": "shortlisted",
        "stage": "Technical Interview",
        "recruiter_note": "Strong match score and relevant Python/SQL expertise."
    })
    assert stage_resp.status_code == 200
    assert stage_resp.json()["status"] == "shortlisted"
    assert stage_resp.json()["stage"] == "Technical Interview"
