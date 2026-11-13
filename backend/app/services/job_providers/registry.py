"""
Central Registry and Coordinator for Live Job Retrieval Providers.
Manages provider routing (Adzuna for India/Metro + Remotive for Remote),
in-memory TTL caching (15 mins), deduplication, and honest diagnostic status.
"""
import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

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

logger = logging.getLogger("inclusive_ats.job_providers.registry")

# 15 minutes TTL for query caching
CACHE_TTL_SECONDS = 900


class JobProviderRegistry:
    """
    Central manager for external job providers.
    Supports querying Adzuna (primary for India / metro cities) and Remotive (worldwide remote),
    with thread-safe TTL caching, cross-provider deduplication, and zero data leakage.
    """

    def __init__(self):
        self._providers: Dict[str, JobProvider] = {
            "adzuna": AdzunaJobProvider(),
            "remotive": RemotiveJobProvider(),
        }
        self._cache: Dict[str, Tuple[float, ProviderSearchResult]] = {}

    def get_provider(self, name: str) -> Optional[JobProvider]:
        return self._providers.get(name)

    def get_providers_status(self) -> Dict[str, Any]:
        """
        Returns full diagnostic status of all registered job providers,
        including documentation links and exact environment variable setup steps.
        """
        adzuna = self._providers["adzuna"]
        remotive = self._providers["remotive"]

        adzuna_status = adzuna.get_status()
        remotive_status = remotive.get_status()

        return {
            "active": settings.ENABLE_EXTERNAL_JOBS,
            "india_live_retrieval_ready": adzuna.is_configured(),
            "providers": {
                "adzuna": adzuna_status,
                "remotive": remotive_status,
            },
            "configuration_guide": {
                "provider": "Adzuna Developer API (India & Global)",
                "official_docs": "https://developer.adzuna.com/docs/search",
                "signup_url": "https://developer.adzuna.com/signup",
                "env_variables": [
                    {
                        "name": "ADZUNA_APP_ID",
                        "description": "Your Adzuna Application ID from developer.adzuna.com",
                        "required": True,
                        "example": "your_adzuna_app_id_here",
                    },
                    {
                        "name": "ADZUNA_APP_KEY",
                        "description": "Your Adzuna Application Key from developer.adzuna.com",
                        "required": True,
                        "example": "your_adzuna_app_key_here",
                    },
                    {
                        "name": "ADZUNA_COUNTRY",
                        "description": "Country code for default search (default: in for India)",
                        "required": False,
                        "default": "in",
                        "example": "in",
                    },
                ],
                "setup_steps": [
                    "1. Register a free developer account at https://developer.adzuna.com/signup",
                    "2. Verify email and navigate to your Adzuna Developer Dashboard.",
                    "3. Copy your Application ID and Application Key.",
                    "4. Add ADZUNA_APP_ID=<your_app_id> and ADZUNA_APP_KEY=<your_app_key> to your backend/.env file.",
                    "5. Restart the backend API server. Live vacancies in Kolkata, Delhi, and India will activate immediately.",
                ],
            },
        }

    def search_live_jobs(self, query: JobSearchQuery) -> ProviderSearchResult:
        """
        Coordinates live search with routing, caching, and deduplication.
        
        Routing Logic:
        1. If query targets an Indian location (Kolkata, Delhi, Bengaluru, etc.) or country="in":
           - Routes primarily to Adzuna (which indexes genuine Indian vacancies).
           - If Adzuna is unconfigured, returns a clear 'unconfigured' status with setup steps.
             Never substitutes fake vacancies or claims live search succeeded without credentials.
           - If work_arrangement != 'on-site', Remotive is queried as a supplement for remote roles open to India.
        2. If query is generic remote:
           - Queries Adzuna (if configured) and Remotive.
        """
        if not settings.ENABLE_EXTERNAL_JOBS:
            return ProviderSearchResult(
                provider="Registry",
                status="unconfigured",
                message="External job retrieval is disabled in server configuration (ENABLE_EXTERNAL_JOBS=False).",
                total=0,
                page=query.page,
                limit=query.limit,
                items=[],
            )

        cache_key = self._make_cache_key(query)
        now = time.time()

        # Check in-memory cache
        if cache_key in self._cache:
            cached_time, cached_result = self._cache[cache_key]
            if now - cached_time < CACHE_TTL_SECONDS:
                logger.debug(f"Returning cached live jobs for key: {cache_key[:12]}")
                # Return a copy with cached=True
                return ProviderSearchResult(
                    provider=cached_result.provider,
                    status=cached_result.status,
                    message=cached_result.message,
                    total=cached_result.total,
                    page=cached_result.page,
                    limit=cached_result.limit,
                    items=cached_result.items,
                    cached=True,
                )

        adzuna = self._providers["adzuna"]
        remotive = self._providers["remotive"]

        is_indian_query = self._is_indian_query(query)
        is_strictly_onsite = query.work_arrangement == "on-site"

        all_items: List[LiveJobListing] = []
        statuses: List[str] = []
        messages: List[str] = []
        provider_names: List[str] = []

        # 1. Execute Adzuna if configured or if specifically required for Indian location
        if adzuna.is_configured():
            adzuna_res = adzuna.search(query)
            statuses.append(adzuna_res.status)
            messages.append(adzuna_res.message)
            provider_names.append("Adzuna")
            if adzuna_res.status == "success":
                all_items.extend(adzuna_res.items)
        else:
            if is_indian_query and is_strictly_onsite:
                # User asked specifically for on-site jobs in Kolkata/Delhi/India, but Adzuna credentials are missing
                return ProviderSearchResult(
                    provider="Adzuna Developer API",
                    status="unconfigured",
                    message=(
                        f"Live search for genuine vacancies in '{query.location or 'India'}' requires Adzuna API credentials. "
                        "Please obtain free credentials from https://developer.adzuna.com/signup and set ADZUNA_APP_ID "
                        "and ADZUNA_APP_KEY in your backend .env file. No mock or fabricated vacancies are substituted."
                    ),
                    total=0,
                    page=query.page,
                    limit=query.limit,
                    items=[],
                )
            elif is_indian_query:
                # Query was for India, Adzuna is unconfigured, but user permits remote or general roles
                messages.append(
                    "Adzuna credentials not configured for local Indian city search; checking remote companion provider."
                )

        # 2. Execute Remotive (for remote roles or supplementary vacancies)
        if not is_strictly_onsite:
            remotive_res = remotive.search(query)
            statuses.append(remotive_res.status)
            provider_names.append("Remotive")
            if remotive_res.status == "success":
                all_items.extend(remotive_res.items)

        # 3. Deduplicate and filter out expired
        deduped = self._deduplicate_and_filter(all_items)

        # Determine overall status
        if all_items:
            final_status = "success"
            active_providers = ", ".join(provider_names)
            final_message = f"Found {len(deduped)} live vacancies via {active_providers}."
        elif not adzuna.is_configured() and is_indian_query:
            final_status = "unconfigured"
            final_message = (
                f"Adzuna API credentials are not configured for live search in '{query.location or 'India'}'. "
                "Get free API keys at https://developer.adzuna.com/signup and set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env."
            )
        elif any(s == "rate_limited" for s in statuses):
            final_status = "rate_limited"
            final_message = "Live search provider rate limit reached. Please wait a moment before trying again."
        elif any(s == "error" for s in statuses):
            final_status = "error"
            final_message = "Live search provider experienced an error or network timeout. Please retry."
        else:
            final_status = "success"
            final_message = f"No live vacancies found matching query criteria."

        # Paginate combined results
        page = max(1, query.page)
        limit = max(1, query.limit)
        start_idx = (page - 1) * limit
        paged_items = deduped[start_idx : start_idx + limit]

        result = ProviderSearchResult(
            provider=" + ".join(provider_names) if provider_names else "Job Provider Registry",
            status=final_status,
            message=final_message,
            total=len(deduped),
            page=page,
            limit=limit,
            items=paged_items,
            cached=False,
        )

        # Only cache successful or empty searches (do not cache transient errors)
        if final_status in ("success", "unconfigured"):
            self._cache[cache_key] = (now, result)

        return result

    @staticmethod
    def _is_indian_query(query: JobSearchQuery) -> bool:
        if query.country.lower() == "in":
            return True
        if query.location:
            loc_lower = query.location.lower()
            return any(city in loc_lower for city in INDIAN_LOCATIONS)
        return False

    @staticmethod
    def _deduplicate_and_filter(items: List[LiveJobListing]) -> List[LiveJobListing]:
        seen_keys: Set[str] = set()
        deduped: List[LiveJobListing] = []

        for item in items:
            # Exclude expired
            if item.expiry_date:
                # If expiry date format is YYYY-MM-DD
                try:
                    exp_ts = time.mktime(time.strptime(item.expiry_date, "%Y-%m-%d"))
                    if exp_ts < time.time():
                        continue
                except Exception:
                    pass

            norm_title = re.sub(r'\W+', '', item.title.lower())
            norm_comp = re.sub(r'\W+', '', item.company_name.lower())
            key = f"{norm_title}::{norm_comp}"

            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(item)

        return deduped

    @staticmethod
    def _make_cache_key(query: JobSearchQuery) -> str:
        raw = (
            f"kw:{query.keywords or ''}|loc:{query.location or ''}|"
            f"ctry:{query.country}|wa:{query.work_arrangement or ''}|"
            f"exp:{query.experience_level or ''}|cat:{query.category or ''}|"
            f"p:{query.page}|l:{query.limit}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Singleton instance
registry = JobProviderRegistry()
