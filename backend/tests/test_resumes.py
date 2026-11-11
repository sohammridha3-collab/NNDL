import io
from docx import Document


def test_upload_txt_resume(client, test_candidate, candidate_token):
    headers = {"Authorization": f"Bearer {candidate_token}"}
    content = b"""
    Summary:
    Experienced Machine Learning Engineer with strong background in NLP and Python.

    Skills:
    Python, PyTorch, SQL, Docker, AWS, Scikit-learn.

    Experience:
    Senior ML Engineer at AI Corp (2020-2024). Developed recommendation models and ATS parsers.

    Education:
    Bachelor of Science in Computer Science, State University.
    """
    files = {"file": ("resume.txt", io.BytesIO(content), "text/plain")}
    response = client.post("/api/v1/resumes/upload", headers=headers, files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["file_name"] == "resume.txt"
    assert data["file_type"] == "txt"
    assert data["ats_score"] > 50.0
    assert "python" in data["skills"]


def test_upload_docx_resume(client, test_candidate, candidate_token):
    headers = {"Authorization": f"Bearer {candidate_token}"}
    doc = Document()
    doc.add_heading("Professional Summary", level=1)
    doc.add_paragraph("Full Stack Software Engineer specializing in React, Node.js and TypeScript.")
    doc.add_heading("Technical Skills", level=1)
    doc.add_paragraph("JavaScript, TypeScript, React, Node.js, Git, MySQL.")
    doc.add_heading("Work Experience", level=1)
    doc.add_paragraph("Software Engineer at WebWorks (2021-2024). Built microservices and web apps.")
    doc.add_heading("Education", level=1)
    doc.add_paragraph("B.S. in Software Engineering.")

    doc_io = io.BytesIO()
    doc.save(doc_io)
    doc_io.seek(0)

    files = {"file": ("my_resume.docx", doc_io, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    response = client.post("/api/v1/resumes/upload", headers=headers, files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["file_name"] == "my_resume.docx"
    assert "react" in data["skills"]


def test_upload_unsupported_file(client, test_candidate, candidate_token):
    headers = {"Authorization": f"Bearer {candidate_token}"}
    files = {"file": ("resume.exe", io.BytesIO(b"executable content"), "application/octet-stream")}
    response = client.post("/api/v1/resumes/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_analyze_resume(client, test_candidate, candidate_token):
    headers = {"Authorization": f"Bearer {candidate_token}"}
    content = b"""
    Summary: Experienced Engineer.
    Experience: 5 years in Python and Docker.
    Education: B.S. in Computer Science.
    Skills: Python, Docker, SQL.
    """
    files = {"file": ("resume.txt", io.BytesIO(content), "text/plain")}
    upload_res = client.post("/api/v1/resumes/upload", headers=headers, files=files)
    resume_id = upload_res.json()["id"]

    analyze_res = client.post(f"/api/v1/resumes/{resume_id}/analyze", headers=headers)
    assert analyze_res.status_code == 200
    data = analyze_res.json()
    assert data["resume_id"] == resume_id
    assert "ats_score" in data
    assert "readability_rating" in data
    assert "extracted_skills" in data
    assert data["sdg10_bias_mitigation_applied"] is True


def test_delete_resume(client, test_candidate, candidate_token):
    headers = {"Authorization": f"Bearer {candidate_token}"}
    files = {"file": ("temp.txt", io.BytesIO(b"Temporary resume text for deletion test with skills: Python."), "text/plain")}
    upload_res = client.post("/api/v1/resumes/upload", headers=headers, files=files)
    resume_id = upload_res.json()["id"]

    del_res = client.delete(f"/api/v1/resumes/{resume_id}", headers=headers)
    assert del_res.status_code == 200

    # Ensure deleted
    get_res = client.get(f"/api/v1/resumes/{resume_id}", headers=headers)
    assert get_res.status_code == 404
