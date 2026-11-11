import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.session import Base, get_db
from app.main import app
from app.models.models import CandidateProfile, Company, Job, RecruiterProfile, User

# Use test SQLite database
TEST_DATABASE_URL = "sqlite:///./test_inclusive_ats.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    try:
        if os.path.exists("./test_inclusive_ats.db"):
            os.remove("./test_inclusive_ats.db")
    except Exception:
        pass


@pytest.fixture
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_candidate(db):
    user = User(
        email="test_candidate@example.com",
        hashed_password=get_password_hash("Password123!"),
        full_name="Alex Morgan",
        role="candidate",
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.flush()
    profile = CandidateProfile(user_id=user.id, target_title="Software Engineer")
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_recruiter(db):
    user = User(
        email="test_recruiter@techcorp.com",
        hashed_password=get_password_hash("Password123!"),
        full_name="Sarah Recruiter",
        role="recruiter",
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.flush()
    company = Company(name="TechCorp Global")
    db.add(company)
    db.flush()
    profile = RecruiterProfile(user_id=user.id, company_id=company.id)
    db.add(profile)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_admin(db):
    user = User(
        email="test_admin@ats.com",
        hashed_password=get_password_hash("Password123!"),
        full_name="System Admin",
        role="admin",
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def candidate_token(test_candidate):
    return create_access_token(subject=test_candidate.id, role="candidate")


@pytest.fixture
def recruiter_token(test_recruiter):
    return create_access_token(subject=test_recruiter.id, role="recruiter")


@pytest.fixture
def admin_token(test_admin):
    return create_access_token(subject=test_admin.id, role="admin")
