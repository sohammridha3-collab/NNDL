"""
External Job Service adaptor delegating to the modular JobProviderRegistry.
Ensures zero candidate data leakage and preserves backward compatibility.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.job_providers.base import JobSearchQuery
from app.services.job_providers.registry import registry

logger = logging.getLogger("inclusive_ats.external_jobs")


class ExternalJobService:
    """
    Adapter service interfacing with the modular JobProviderRegistry.
    Guarantees:
    1. Zero Private Data Leakage: Only sanitized public skill keywords and job location.
       Raw resume text, names, emails, and candidate identifiers are NEVER transmitted or logged.
    2. Resilient Graceful Degradation: If API keys are missing, falls back cleanly without crashing.
    3. Thread-safe 15-minute TTL caching and deduplication.
    4. Clear attribution: live vacancies are distinctly tagged from dataset listings.
    """

    @classmethod
    def get_api_status(cls) -> Dict[str, Any]:
        """Returns the diagnostic status of registered external job providers."""
        status_info = registry.get_providers_status()
        adzuna_info = status_info["providers"]["adzuna"]
        remotive_info = status_info["providers"]["remotive"]

        return {
            "provider": "Adzuna Developer API",
            "configured": adzuna_info["configured"],
            "status": "active" if adzuna_info["configured"] else "unconfigured",
            "country": adzuna_info.get("default_country", "in"),
            "fallback_provider": "Remotive Open Jobs API",
            "fallback_active": remotive_info["configured"],
            "supports_indian_locations": True,
            "message": (
                "Authorized Adzuna API connected. Live vacancies in Kolkata, Delhi, and India enabled."
                if adzuna_info["configured"]
                else (
                    "Adzuna API credentials (ADZUNA_APP_ID / ADZUNA_APP_KEY) are not set in .env. "
                    "Live search across Indian cities (Kolkata, Delhi, Bengaluru) requires free Adzuna registration. "
                    "Remote companion vacancies served via Remotive Open API."
                )
            ),
            "configuration_guide": status_info["configuration_guide"],
        }

    @classmethod
    def fetch_jobs(
        cls,
        skills: Optional[List[str]] = None,
        location: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 15,
        page: int = 1,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Retrieves live job vacancies matching the given skill keywords.
        Returns (jobs_list, api_status_dict).
        """
        if not settings.ENABLE_EXTERNAL_JOBS:
            return [], {
                "provider": "None",
                "configured": False,
                "status": "disabled",
                "message": "External job retrieval is disabled in server configuration.",
            }

        # Clean sanitized search keywords (only take top 3-4 skills for clean API query)
        safe_keywords = [
            re.sub(r'[^a-zA-Z0-9+#. ]', '', s).strip()
            for s in (skills or [])
            if s and len(s.strip()) > 1
        ][:4]

        query_terms = " ".join(safe_keywords) if safe_keywords else ""

        query = JobSearchQuery(
            keywords=query_terms or None,
            location=location or None,
            country=settings.ADZUNA_COUNTRY or "in",
            work_arrangement=job_type,
            page=page,
            limit=limit,
        )

        search_result = registry.search_live_jobs(query)

        # Convert normalized LiveJobListing objects to dictionaries
        formatted_items: List[Dict[str, Any]] = []
        for it in search_result.items:
            formatted_items.append({
                "id": it.source_id,
                "job_code": it.source_id,
                "title": it.title,
                "company_name": it.company_name,
                "location": it.location,
                "job_type": it.job_type,
                "experience_level": it.experience_level or "Mid-Level",
                "category": it.category or "Information Technology",
                "description": it.description,
                "requirements": " ".join(it.available_requirements) if it.available_requirements else "See live posting for details.",
                "min_salary": it.min_salary,
                "max_salary": it.max_salary,
                "salary_currency": it.salary_currency or "INR",
                "posted_date": it.posting_date or "Recently posted",
                "source_type": "live_vacancy",
                "source_label": it.source_label,
                "external_url": it.application_url or it.source_url,
                "status": "active",
                "available_requirements": it.available_requirements,
                "is_live": True,
            })

        status_dict = cls.get_api_status()
        status_dict["search_status"] = search_result.status
        status_dict["search_message"] = search_result.message
        status_dict["cached"] = search_result.cached
        status_dict["total"] = search_result.total

        return formatted_items, status_dict
