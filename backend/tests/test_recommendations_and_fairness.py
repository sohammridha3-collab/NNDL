import io


def test_job_recommendations(client, test_candidate, candidate_token, test_recruiter, recruiter_token):
    # Upload candidate resume
    cand_headers = {"Authorization": f"Bearer {candidate_token}"}
    resume_content = b"""
    Summary: AI & Data Specialist.
    Skills: Python, Machine Learning, SQL, Pandas, NumPy.
    Experience: 3 years building predictive models and data pipelines.
    Education: B.S. in Data Science.
    """
    files = {"file": ("data_scientist.txt", io.BytesIO(resume_content), "text/plain")}
    client.post("/api/v1/resumes/upload", headers=cand_headers, files=files)

    # Post jobs
    rec_headers = {"Authorization": f"Bearer {recruiter_token}"}
    client.post("/api/v1/jobs", headers=rec_headers, json={
        "title": "Machine Learning Engineer",
        "category": "Data Science",
        "description": "Looking for ML Engineer with Python, Machine Learning, and SQL.",
        "skills": ["python", "machine learning", "sql"]
    })
    client.post("/api/v1/jobs", headers=rec_headers, json={
        "title": "Accountant",
        "category": "Finance",
        "description": "Requires Accounting and Budgeting experience.",
        "skills": ["accounting", "budgeting"]
    })

    # Request recommendations
    rec_resp = client.get("/api/v1/recommendations/jobs?limit=5", headers=cand_headers)
    assert rec_resp.status_code == 200
    data = rec_resp.json()
    assert "recommendations" in data
    assert len(data["recommendations"]) >= 1
    # Machine Learning Engineer should rank higher than Accountant
    top_rec = data["recommendations"][0]
    assert "Machine Learning" in top_rec["title"]


def test_fairness_audit(client, test_admin, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    audit_resp = client.post("/api/v1/fairness/audit", headers=headers, json={
        "name": "SDG 10 Test Verification Audit"
    })
    assert audit_resp.status_code == 200
    data = audit_resp.json()
    assert "audit_id" in data
    assert "demographic_parity_summary" in data
    assert "counterfactual_sensitivity_results" in data
    assert "overall_fairness_verdict" in data
    assert data["demographic_parity_summary"]["demographic_bias_reduction_percentage"] >= 90.0

    # Retrieve reports
    reports_resp = client.get("/api/v1/fairness/reports", headers=headers)
    assert reports_resp.status_code == 200
    reports = reports_resp.json()
    assert len(reports) >= 1


def test_dashboards(client, test_candidate, candidate_token, test_recruiter, recruiter_token, test_admin, admin_token):
    # Candidate dashboard
    cand_resp = client.get("/api/v1/dashboard/candidate", headers={"Authorization": f"Bearer {candidate_token}"})
    assert cand_resp.status_code == 200
    assert "total_applications" in cand_resp.json()

    # Recruiter dashboard
    rec_resp = client.get("/api/v1/dashboard/recruiter", headers={"Authorization": f"Bearer {recruiter_token}"})
    assert rec_resp.status_code == 200
    assert "total_active_jobs" in rec_resp.json()

    # Admin dashboard
    admin_resp = client.get("/api/v1/dashboard/admin", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_resp.status_code == 200
    assert "total_users" in admin_resp.json()
    assert "system_health" in admin_resp.json()
