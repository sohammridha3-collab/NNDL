import os
import sys

# Critical for PyTorch / OpenMP multi-thread stability on Windows
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

sys.path.insert(0, 'backend')

from tests.test_live_job_providers import (
    test_job_provider_interface_compliance,
    test_adzuna_indian_locations_routing,
    test_adzuna_unconfigured_state_no_fake_jobs,
    test_adzuna_response_normalization,
    test_remotive_provider_filtering,
    test_registry_deduplication_and_caching,
)

print("Running test_job_provider_interface_compliance...", flush=True)
test_job_provider_interface_compliance()
print("PASS: test_job_provider_interface_compliance", flush=True)

print("Running test_adzuna_indian_locations_routing...", flush=True)
test_adzuna_indian_locations_routing()
print("PASS: test_adzuna_indian_locations_routing", flush=True)

print("Running test_adzuna_unconfigured_state_no_fake_jobs...", flush=True)
test_adzuna_unconfigured_state_no_fake_jobs()
print("PASS: test_adzuna_unconfigured_state_no_fake_jobs", flush=True)

print("Running test_adzuna_response_normalization...", flush=True)
test_adzuna_response_normalization()
print("PASS: test_adzuna_response_normalization", flush=True)

print("Running test_remotive_provider_filtering...", flush=True)
test_remotive_provider_filtering()
print("PASS: test_remotive_provider_filtering", flush=True)

print("Running test_registry_deduplication_and_caching...", flush=True)
test_registry_deduplication_and_caching()
print("PASS: test_registry_deduplication_and_caching", flush=True)

# API Endpoint Tests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.jobs import router as jobs_router
from unittest.mock import patch
from app.core.config import settings

test_app = FastAPI()
test_app.include_router(jobs_router, prefix="/api/v1")
api_client = TestClient(test_app)

print("\nRunning API status endpoint test...", flush=True)
res = api_client.get("/api/v1/jobs/live/status")
assert res.status_code == 200
data = res.json()
assert data["active"] is True
assert "adzuna" in data["providers"]
assert "remotive" in data["providers"]
assert "developer.adzuna.com" in str(data["configuration_guide"])
print("PASS: GET /api/v1/jobs/live/status returned 200 with complete diagnostics & setup guide", flush=True)

print("\nRunning API search endpoint test (unconfigured Indian city)...", flush=True)
with patch.object(settings, "ADZUNA_APP_ID", ""), patch.object(settings, "ADZUNA_APP_KEY", ""):
    res = api_client.get("/api/v1/jobs/live/search?location=Kolkata&work_arrangement=on-site")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unconfigured"
    assert data["items"] == []
    assert data["total"] == 0
    assert "Kolkata" in data["message"]
    assert "https://developer.adzuna.com/signup" in data["message"]
print("PASS: GET /api/v1/jobs/live/search gracefully handles unconfigured Indian city without mock data", flush=True)

print("\n=======================================================", flush=True)
print("ALL 8 PROVIDER AND API TESTS COMPLETED AND VERIFIED!", flush=True)
print("=======================================================", flush=True)
