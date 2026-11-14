"""
End-to-End Simulation of Frontend Browser Requests to Backend on Port 8001.
Simulates exact headers, Origins, and workflows executed by frontend JavaScript modules.
"""
import json
import io
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

BACKEND_URL = "http://127.0.0.1:8001"
FRONTEND_ORIGIN = "http://127.0.0.1:5500"


def make_request(path, method="GET", body=None, headers=None, content_type="application/json"):
    url = f"{BACKEND_URL}{path}"
    h = {
        "Origin": FRONTEND_ORIGIN,
        "Accept": "application/json"
    }
    if headers:
        h.update(headers)

    data = None
    if body is not None:
        if isinstance(body, bytes):
            data = body
            h["Content-Type"] = content_type
        elif isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            parsed = {}
            if resp_body and resp_body.strip():
                try:
                    parsed = json.loads(resp_body)
                except Exception:
                    parsed = resp_body
            return resp.status, resp.headers, parsed
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        parsed = {}
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"raw": err_body}
        return e.code, e.headers, parsed


def test_full_browser_journey():
    print("=" * 76)
    print("  SIMULATING FULL BROWSER JOURNEY (Origin: http://127.0.0.1:5500)")
    print("=" * 76)

    # 1. Health Probe
    status, headers, body = make_request("/health")
    assert status == 200, f"Health failed: {status}"
    assert headers.get("Access-Control-Allow-Origin") == FRONTEND_ORIGIN
    print(f"  ✓ [1] GET /health                      : {status} OK (service: {body.get('service')})")

    # 2. Readiness Probe
    status, headers, body = make_request("/ready?wait=60")
    assert status == 200, f"Readiness failed: {status}"
    print(f"  ✓ [2] GET /ready                       : {status} OK (db: {body.get('database')}, model: {body.get('ml_model')})")

    # 3. OpenAPI Schema
    status, headers, body = make_request("/openapi.json")
    assert status == 200, f"OpenAPI failed: {status}"
    print(f"  ✓ [3] GET /openapi.json                : {status} OK (paths: {len(body.get('paths', {}))})")

    # 4. CORS Preflight OPTIONS
    status, headers, _ = make_request(
        "/api/v1/auth/login",
        method="OPTIONS",
        headers={
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization"
        }
    )
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") == FRONTEND_ORIGIN
    assert headers.get("Access-Control-Allow-Credentials") == "true"
    print(f"  ✓ [4] OPTIONS /api/v1/auth/login       : {status} Preflight Approved")

    # 5. Candidate Registration
    import time
    email = f"candidate_{int(time.time())}@example.com"
    reg_payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Verified Candidate",
        "role": "candidate"
    }
    status, headers, reg_data = make_request("/api/v1/auth/register", method="POST", body=reg_payload)
    assert status == 201, f"Registration failed: {status} {reg_data}"
    access_token = reg_data["access_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    print(f"  ✓ [5] POST /api/v1/auth/register       : {status} Created ({email})")

    # 6. Candidate Login Verification
    status, headers, login_data = make_request("/api/v1/auth/login", method="POST", body={
        "email": email,
        "password": "Password123!"
    })
    assert status == 200, f"Login failed: {status}"
    print(f"  ✓ [6] POST /api/v1/auth/login          : {status} Authenticated successfully")

    # 7. Candidate Dashboard
    status, headers, dash_data = make_request("/api/v1/dashboard/candidate", headers=auth_headers)
    assert status == 200, f"Dashboard failed: {status}"
    print(f"  ✓ [7] GET /api/v1/dashboard/candidate  : {status} OK (applications: {len(dash_data.get('applications', []))})")

    # 8. Resume Upload (Multipart form-data)
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    resume_content = (
        "Experienced Python Developer\n"
        "Skills: Python, FastAPI, PyTorch, Docker, SQL, Machine Learning\n"
        "Experience: 4 years backend development and ML engineering\n"
        "Education: Bachelor of Technology in Computer Science\n"
    )
    body_parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Disposition: form-data; name="file"; filename="test_resume.txt"\r\n',
        b'Content-Type: text/plain\r\n\r\n',
        resume_content.encode("utf-8"),
        f"\r\n--{boundary}--\r\n".encode("utf-8")
    ]
    multipart_body = b"".join(body_parts)
    status, headers, upload_data = make_request(
        "/api/v1/resumes/upload",
        method="POST",
        body=multipart_body,
        headers=auth_headers,
        content_type=f"multipart/form-data; boundary={boundary}"
    )
    assert status == 201, f"Upload failed: {status} {upload_data}"
    resume_id = upload_data["id"]
    print(f"  ✓ [8] POST /api/v1/resumes/upload      : {status} Uploaded resume_id={resume_id}")

    # 9. Resume Analysis
    status, headers, analysis_data = make_request(f"/api/v1/resumes/{resume_id}/analyze", method="POST", headers=auth_headers)
    assert status == 200, f"Analyze failed: {status}"
    ats_score = analysis_data.get("ats_score", 0.0)
    print(f"  ✓ [9] POST /api/v1/resumes/.../analyze : {status} ATS Score={ats_score:.1f}%")

    # 10. Dashboard Job Recommendations
    status, headers, recs_data = make_request("/api/v1/recommendations/jobs?limit=5", headers=auth_headers)
    assert status == 200, f"Recommendations failed: {status}"
    items = recs_data.get("recommendations", [])
    print(f"  ✓ [10] GET /recommendations/jobs       : {status} OK ({len(items)} recommendations returned)")
    if items:
        first = items[0]
        # Verify dashboard.js contract keys
        assert "job_id" in first
        assert "compatibility_score" in first
        assert "recommendation_reason" in first
        print(f"         First Match: '{first.get('title')}' at '{first.get('company_name')}' (Score: {first.get('compatibility_score')}%)")

    # 11. Skill-Based Recommendations
    skill_req = {
        "skills": ["python", "docker", "sql"],
        "location": "Kolkata",
        "limit": 5,
        "include_external": False
    }
    status, headers, skill_data = make_request("/api/v1/recommendations/skills", method="POST", body=skill_req, headers=auth_headers)
    assert status == 200, f"Skill recs failed: {status}"
    print(f"  ✓ [11] POST /recommendations/skills    : {status} OK (found: {skill_data.get('total')})")

    print("\n" + "=" * 76)
    print("  ALL 11 BROWSER REQUESTS SUCCEEDED WITH 200/201 STATUS AND VALID CORS!")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    test_full_browser_journey()
