"""
Unit and integration tests for live job retrieval providers (Adzuna and Remotive),
Indian location routing (Kolkata, Delhi, Bengaluru), registry caching, deduplication,
and zero data leakage / zero fabrication guarantees.
"""
import os
import sys

# Windows PyTorch / OpenMP multi-thread stability
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import pytest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.job_providers.base import (
    JobProvider,
    JobSearchQuery,
    LiveJobListing,
    ProviderSearchResult,
)
from app.services.job_providers.adzuna_provider import (
    AdzunaJobProvider,
    INDIAN_LOCATIONS,
)
from app.services.job_providers.remotive_provider import RemotiveJobProvider
from app.services.job_providers.registry import JobProviderRegistry


# ======================================================================
# 1. INTERFACE COMPLIANCE TESTS
# ======================================================================
def test_job_provider_interface_compliance():
    """Verify that both Adzuna and Remotive strictly implement the abstract JobProvider contract."""
    adzuna = AdzunaJobProvider()
    remotive = RemotiveJobProvider()

    assert isinstance(adzuna, JobProvider)
    assert isinstance(remotive, JobProvider)

    # Both must implement name, is_configured, get_status, search
    assert hasattr(adzuna, "name") and adzuna.name == "adzuna"
    assert hasattr(remotive, "name") and remotive.name == "remotive"

    assert callable(adzuna.is_configured)
    assert callable(adzuna.get_status)
    assert callable(adzuna.search)

    assert callable(remotive.is_configured)
    assert callable(remotive.get_status)
    assert callable(remotive.search)


# ======================================================================
# 2. INDIAN LOCATION ROUTING & COUNTRY RESOLUTION
# ======================================================================
def test_adzuna_indian_locations_routing():
    """Verify that Indian metro queries (Kolkata, Delhi, Bengaluru, etc.) automatically route to country='in'."""
    adzuna = AdzunaJobProvider()

    # Kolkata query must resolve to India
    assert adzuna._resolve_country(requested_country="us", location="Kolkata, West Bengal") == "in"
    assert adzuna._resolve_country(requested_country="gb", location="New Delhi") == "in"
    assert adzuna._resolve_country(requested_country=None, location="Bengaluru Tech Park") == "in"
    assert adzuna._resolve_country(requested_country=None, location="Mumbai") == "in"

    # Non-Indian location uses requested or default country
    assert adzuna._resolve_country(requested_country="gb", location="London") == "gb"


# ======================================================================
# 3. UNCONFIGURED STATE & ZERO FABRICATION
# ======================================================================
def test_adzuna_unconfigured_state_no_fake_jobs():
    """
    Verify that when Adzuna API credentials are missing from .env,
    the provider reports status='unconfigured' with zero fabricated vacancies.
    """
    adzuna = AdzunaJobProvider()

    with patch.object(settings, "ADZUNA_APP_ID", ""), patch.object(settings, "ADZUNA_APP_KEY", ""):
        assert adzuna.is_configured() is False

        status = adzuna.get_status()
        assert status["configured"] is False
        assert "signup" in status["developer_portal"]

        query = JobSearchQuery(keywords="python developer", location="Kolkata", country="in")
        result = adzuna.search(query)

        assert isinstance(result, ProviderSearchResult)
        assert result.status == "unconfigured"
        assert result.items == []
        assert result.total == 0
        assert "https://developer.adzuna.com/signup" in result.message


# ======================================================================
# 4. NORMALIZATION & CLEANING TESTS
# ======================================================================
def test_adzuna_response_normalization():
    """Verify that Adzuna API responses are cleanly normalized into LiveJobListing with INR currency."""
    adzuna = AdzunaJobProvider()

    raw_items = [
        {
            "id": "12345678",
            "title": "Senior &amp; Python Engineer",
            "company": {"display_name": "Kolkata Analytics Ltd"},
            "location": {"display_name": "Kolkata, West Bengal"},
            "description": "We are seeking a <b>Python</b> engineer with <i>Docker</i> and SQL skills.",
            "created": "2026-11-10T10:00:00Z",
            "redirect_url": "https://www.adzuna.in/land/ad/12345678",
            "salary_min": 800000.0,
            "salary_max": 1400000.0,
            "category": {"label": "IT Jobs"}
        }
    ]

    query = JobSearchQuery(keywords="python", location="Kolkata", country="in")
    listings = adzuna._normalize_items(raw_items, country="in", query=query)

    assert len(listings) == 1
    job = listings[0]

    assert isinstance(job, LiveJobListing)
    assert job.source_id == "adzuna:12345678"
    assert job.source_provider == "adzuna"
    assert job.title == "Senior & Python Engineer"  # HTML entity decoded
    assert job.company_name == "Kolkata Analytics Ltd"
    assert job.location == "Kolkata, West Bengal"
    assert job.country == "IN"
    assert job.salary_currency == "INR"
    assert job.min_salary == 800000.0
    assert job.max_salary == 1400000.0
    assert job.is_live is True
    assert "<b>" not in job.description
    assert job.application_url == "https://www.adzuna.in/land/ad/12345678"
    # Extracted technical skills
    assert any("python" in s.lower() for s in job.available_requirements)


# ======================================================================
# 5. REMOTIVE COMPANION PROVIDER
# ======================================================================
def test_remotive_provider_filtering():
    """Verify Remotive provider behavior for remote vs strictly on-site roles."""
    remotive = RemotiveJobProvider()

    assert remotive.is_configured() is True
    status = remotive.get_status()
    assert status["configured"] is True

    # When query strictly requires on-site, Remotive returns 0 items
    onsite_query = JobSearchQuery(keywords="python", work_arrangement="on-site")
    onsite_result = remotive.search(onsite_query)
    assert onsite_result.status == "success"
    assert onsite_result.items == []
    assert onsite_result.total == 0


# ======================================================================
# 6. REGISTRY DEDUPLICATION AND CACHING
# ======================================================================
def test_registry_deduplication_and_caching():
    """Verify registry deduplicates identical postings and caches repeated queries."""
    reg = JobProviderRegistry()

    item1 = LiveJobListing(
        source_id="adzuna:1",
        source_provider="adzuna",
        source_label="Live Vacancy (Adzuna - IN)",
        title="Full Stack Developer",
        company_name="TechCorp India",
        description="Great role",
        location="Kolkata",
        country="IN",
        is_live=True
    )
    item2 = LiveJobListing(
        source_id="remotive:2",
        source_provider="remotive",
        source_label="Live Vacancy (Remotive)",
        title="Full Stack Developer",  # Duplicate title & company
        company_name="TechCorp India",
        description="Great role duplicate",
        location="Remote",
        country=None,
        is_live=True
    )
    item3 = LiveJobListing(
        source_id="adzuna:3",
        source_provider="adzuna",
        source_label="Live Vacancy (Adzuna - IN)",
        title="DevOps Engineer",
        company_name="Cloud Solutions Delhi",
        description="Kubernetes & Terraform",
        location="Delhi",
        country="IN",
        is_live=True
    )

    deduped = reg._deduplicate_and_filter([item1, item2, item3])
    assert len(deduped) == 2  # item2 collapsed into item1
    titles = [d.title for d in deduped]
    assert "Full Stack Developer" in titles
    assert "DevOps Engineer" in titles


# ======================================================================
# 7. FASTAPI ENDPOINT INTEGRATION TESTS
# ======================================================================
def test_live_jobs_status_api(client):
    """Verify GET /api/v1/jobs/live/status returns diagnostic info and setup guide."""
    res = client.get("/api/v1/jobs/live/status")
    assert res.status_code == 200
    data = res.json()

    assert "active" in data
    assert "providers" in data
    assert "adzuna" in data["providers"]
    assert "remotive" in data["providers"]
    assert "configuration_guide" in data
    assert "https://developer.adzuna.com/signup" in str(data["configuration_guide"])


def test_live_jobs_search_api_unconfigured_indian_city(client):
    """
    Verify GET /api/v1/jobs/live/search gracefully handles unconfigured Indian city search
    without returning fake listings or failing with 500 error.
    """
    with patch.object(settings, "ADZUNA_APP_ID", ""), patch.object(settings, "ADZUNA_APP_KEY", ""):
        res = client.get("/api/v1/jobs/live/search?location=Kolkata&work_arrangement=on-site")
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "unconfigured"
        assert data["items"] == []
        assert data["total"] == 0
        assert "Kolkata" in data["message"]
        assert "https://developer.adzuna.com/signup" in data["message"]
