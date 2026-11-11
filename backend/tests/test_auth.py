def test_register_candidate(client):
    payload = {
        "email": "new_cand@example.com",
        "password": "SecurePassword123",
        "full_name": "Jordan Lee",
        "role": "candidate"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "new_cand@example.com"
    assert data["user"]["role"] == "candidate"


def test_register_recruiter(client):
    payload = {
        "email": "new_recruiter@innovate.com",
        "password": "SecurePassword123",
        "full_name": "Marcus Stone",
        "role": "recruiter",
        "company_name": "Innovate Labs"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["role"] == "recruiter"


def test_register_duplicate_email(client, test_candidate):
    payload = {
        "email": test_candidate.email,
        "password": "Password123!",
        "full_name": "Duplicate Candidate",
        "role": "candidate"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_login_success(client, test_candidate):
    payload = {
        "email": test_candidate.email,
        "password": "Password123!"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == test_candidate.email


def test_login_wrong_password(client, test_candidate):
    payload = {
        "email": test_candidate.email,
        "password": "WrongPassword999"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


def test_get_me_authenticated(client, test_candidate, candidate_token):
    headers = {"Authorization": f"Bearer {candidate_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_candidate.id
    assert data["email"] == test_candidate.email


def test_get_me_unauthenticated(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_refresh_token(client, test_candidate):
    login_resp = client.post("/api/v1/auth/login", json={
        "email": test_candidate.email,
        "password": "Password123!"
    })
    refresh_tok = login_resp.json()["refresh_token"]

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_tok})
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
