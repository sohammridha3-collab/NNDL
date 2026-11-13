"""
Adzuna Job Search Provider implementation supporting India (Kolkata, Delhi, etc.) and global markets.
Official Developer Documentation: https://developer.adzuna.com/docs/search
"""
import html
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.ml.preprocessing import DEFAULT_SKILLS, extract_skills
from app.services.job_providers.base import (
    JobProvider,
    JobSearchQuery,
    LiveJobListing,
    ProviderSearchResult,
)

logger = logging.getLogger("inclusive_ats.job_providers.adzuna")

# Supported countries by Adzuna API
SUPPORTED_ADZUNA_COUNTRIES = {
    "in", "gb", "us", "at", "au", "be", "br", "ca", "de", "es", "fr", "it", "nl", "nz", "pl", "ru", "sg", "za"
}

# Major Indian metros and tech hubs for automatic country routing
INDIAN_LOCATIONS = {
    "kolkata", "delhi", "new delhi", "noida", "gurgaon", "gurugram", "bengaluru", "bangalore",
    "mumbai", "pune", "hyderabad", "chennai", "ahmedabad", "chandigarh", "jaipur", "kochi",
    "indore", "lucknow", "bhubaneswar", "india"
}


class AdzunaJobProvider(JobProvider):
    name = "adzuna"

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_key: Optional[str] = None,
        default_country: Optional[str] = None
    ):
        self._app_id = app_id
        self._app_key = app_key
        self._default_country = default_country

    @property
    def app_id(self) -> Optional[str]:
        if self._app_id:
            return self._app_id.strip()
        return settings.ADZUNA_APP_ID.strip() if settings.ADZUNA_APP_ID else None

    @property
    def app_key(self) -> Optional[str]:
        if self._app_key:
            return self._app_key.strip()
        return settings.ADZUNA_APP_KEY.strip() if settings.ADZUNA_APP_KEY else None

    @property
    def default_country(self) -> str:
        if self._default_country:
            return self._default_country.strip().lower()
        return (settings.ADZUNA_COUNTRY or "in").strip().lower()

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def get_status(self) -> Dict[str, Any]:
        configured = self.is_configured()
        country = self.default_country
        return {
            "provider": "Adzuna Developer API",
            "name": self.name,
            "configured": configured,
            "default_country": country,
            "supported_countries": sorted(list(SUPPORTED_ADZUNA_COUNTRIES)),
            "supports_indian_locations": True,
            "official_documentation": "https://developer.adzuna.com/docs/search",
            "developer_portal": "https://developer.adzuna.com/signup",
            "required_env_vars": ["ADZUNA_APP_ID", "ADZUNA_APP_KEY", "ADZUNA_COUNTRY"],
            "message": (
                "Adzuna API is fully configured. Live vacancies across India (Kolkata, Delhi, etc.) enabled."
                if configured
                else (
                    "Adzuna Developer API credentials (ADZUNA_APP_ID / ADZUNA_APP_KEY) are not set in .env. "
                    "Register for free at https://developer.adzuna.com/signup to enable live vacancies across Kolkata, Delhi and Indian cities."
                )
            )
        }

    def search(self, query: JobSearchQuery) -> ProviderSearchResult:
        if not self.is_configured():
            return ProviderSearchResult(
                provider="Adzuna Developer API",
                status="unconfigured",
                message=(
                    "Adzuna API credentials are not configured. To search live vacancies across Kolkata, "
                    "Delhi and other Indian locations, obtain free credentials from https://developer.adzuna.com/signup "
                    "and add ADZUNA_APP_ID and ADZUNA_APP_KEY to your backend .env file."
                ),
                total=0,
                page=query.page,
                limit=query.limit,
                items=[]
            )

        # Resolve target country
        country = self._resolve_country(query.country, query.location)
        page = max(1, query.page)
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

        # Clean sanitized query keywords
        raw_keywords = (query.keywords or "").strip()
        safe_keywords = re.sub(r'[^a-zA-Z0-9+#. ]', ' ', raw_keywords)
        safe_keywords = re.sub(r'\s+', ' ', safe_keywords).strip()

        params: Dict[str, Any] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": min(query.limit, 50),
            "content-type": "application/json"
        }

        if safe_keywords:
            params["what"] = safe_keywords

        if query.location and query.location.strip():
            params["where"] = query.location.strip()

        if query.max_days_old:
            params["max_days_old"] = query.max_days_old

        # Handle work arrangement filter at API level where possible
        if query.work_arrangement == "remote":
            # For remote, if location is not set or general, append remote to what
            if not query.location:
                params["what"] = f"{params.get('what', '')} remote".strip()

        logger.info(f"Querying Adzuna API for country='{country}', location='{query.location}', keywords='{safe_keywords}'")

        try:
            timeout_cfg = httpx.Timeout(timeout=6.0, connect=3.0)
            with httpx.Client(timeout=timeout_cfg) as client:
                resp = client.get(url, params=params)

                if resp.status_code == 200:
                    data = resp.json()
                    total_count = data.get("count", 0)
                    raw_items = data.get("results", [])
                    
                    listings = self._normalize_items(raw_items, country=country, query=query)
                    
                    return ProviderSearchResult(
                        provider="Adzuna Developer API",
                        status="success",
                        message=(
                            f"Retrieved {len(listings)} live vacancies from Adzuna ({country.upper()})."
                            if listings
                            else f"No live vacancies found matching '{safe_keywords}' in '{query.location or country.upper()}'."
                        ),
                        total=total_count,
                        page=page,
                        limit=query.limit,
                        items=listings
                    )

                elif resp.status_code == 429:
                    logger.warning("Adzuna API rate limit exceeded (HTTP 429).")
                    return ProviderSearchResult(
                        provider="Adzuna Developer API",
                        status="rate_limited",
                        message="Adzuna developer tier rate limit reached. Please wait a moment before searching again.",
                        total=0,
                        page=page,
                        limit=query.limit,
                        items=[]
                    )

                elif resp.status_code in (400, 401, 403):
                    err_msg = resp.text[:250]
                    logger.error(f"Adzuna API authentication or request error (HTTP {resp.status_code}): {err_msg}")
                    return ProviderSearchResult(
                        provider="Adzuna Developer API",
                        status="error",
                        message=(
                            f"Adzuna API request rejected (HTTP {resp.status_code}). "
                            "Please verify that ADZUNA_APP_ID and ADZUNA_APP_KEY in your .env are valid and authorized for country '{country}'."
                        ),
                        total=0,
                        page=page,
                        limit=query.limit,
                        items=[]
                    )

                else:
                    logger.warning(f"Adzuna API responded with unexpected HTTP {resp.status_code}: {resp.text[:200]}")
                    return ProviderSearchResult(
                        provider="Adzuna Developer API",
                        status="error",
                        message=f"Adzuna API temporarily unavailable (HTTP {resp.status_code}).",
                        total=0,
                        page=page,
                        limit=query.limit,
                        items=[]
                    )

        except httpx.TimeoutException:
            logger.warning("Adzuna API request timed out after 6.0 seconds.")
            return ProviderSearchResult(
                provider="Adzuna Developer API",
                status="error",
                message="Adzuna API request timed out. Please try again.",
                total=0,
                page=page,
                limit=query.limit,
                items=[]
            )
        except Exception as e:
            logger.error(f"Adzuna API connection exception: {e}", exc_info=True)
            return ProviderSearchResult(
                provider="Adzuna Developer API",
                status="error",
                message=f"Could not connect to Adzuna API: {e}",
                total=0,
                page=page,
                limit=query.limit,
                items=[]
            )

    def _resolve_country(self, requested_country: Optional[str], location: Optional[str]) -> str:
        """
        Determines country code, prioritizing Indian cities (Kolkata, Delhi, etc.)
        when specified in the location query.
        """
        if location:
            loc_lower = location.lower()
            if any(ind_city in loc_lower for ind_city in INDIAN_LOCATIONS):
                return "in"

        if requested_country and requested_country.lower().strip() in SUPPORTED_ADZUNA_COUNTRIES:
            return requested_country.lower().strip()

        config_country = (settings.ADZUNA_COUNTRY or "in").lower().strip()
        if config_country in SUPPORTED_ADZUNA_COUNTRIES:
            return config_country

        return "in"

    def _normalize_items(
        self,
        raw_items: List[Dict[str, Any]],
        country: str,
        query: JobSearchQuery
    ) -> List[LiveJobListing]:
        listings: List[LiveJobListing] = []

        currency_map = {
            "in": "INR",
            "us": "USD",
            "gb": "GBP",
            "ca": "CAD",
            "au": "AUD",
            "de": "EUR",
            "fr": "EUR",
            "es": "EUR",
            "it": "EUR",
            "nl": "EUR",
            "at": "EUR",
            "be": "EUR"
        }
        default_currency = currency_map.get(country, "INR")

        for it in raw_items:
            raw_title = it.get("title", "").strip()
            # Clean HTML entities from title
            title = html.unescape(re.sub(r'<[^>]+>', ' ', raw_title)).strip()

            company_obj = it.get("company", {})
            company_name = company_obj.get("display_name", "Verified Employer") if isinstance(company_obj, dict) else "Verified Employer"

            location_obj = it.get("location", {})
            location_name = location_obj.get("display_name", "India") if isinstance(location_obj, dict) else "India"

            raw_desc = it.get("description", "")
            clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', raw_desc)).strip()

            created_date = it.get("created")
            if created_date and "T" in created_date:
                created_date = created_date.split("T")[0]

            job_id = f"adzuna:{it.get('id', '')}"
            redirect_url = it.get("redirect_url")

            # Extract recognized technical skill tokens from description
            matched_skills = sorted(list(extract_skills(f"{title} {clean_desc}".lower(), DEFAULT_SKILLS)))

            # Infer work arrangement
            combined_text = f"{title} {location_name} {clean_desc}".lower()
            if "remote" in combined_text or "work from home" in combined_text or "wfh" in combined_text:
                job_type = "remote"
            elif "hybrid" in combined_text:
                job_type = "hybrid"
            else:
                job_type = "on-site"

            # Filter by work arrangement if requested
            if query.work_arrangement and query.work_arrangement != "all":
                if query.work_arrangement.lower() != job_type:
                    continue

            # Infer experience level
            experience_level = self._infer_experience_level(title, clean_desc)
            if query.experience_level and query.experience_level.lower() not in experience_level.lower():
                continue

            # Category
            category_obj = it.get("category", {})
            category = category_obj.get("label") if isinstance(category_obj, dict) else self._infer_category(title, clean_desc)

            listings.append(
                LiveJobListing(
                    source_id=job_id,
                    source_provider="adzuna",
                    source_label=f"Live Vacancy (Adzuna - {country.upper()})",
                    title=title,
                    company_name=company_name,
                    description=clean_desc,
                    location=location_name,
                    country=country.upper(),
                    available_requirements=matched_skills[:8],
                    source_url=redirect_url,
                    application_url=redirect_url,
                    posting_date=created_date,
                    expiry_date=None,  # Adzuna does not supply static expiry dates
                    min_salary=it.get("salary_min"),
                    max_salary=it.get("salary_max"),
                    salary_currency=default_currency,
                    job_type=job_type,
                    experience_level=experience_level,
                    category=category,
                    is_live=True
                )
            )

        return listings

    @staticmethod
    def _infer_experience_level(title: str, desc: str) -> str:
        text = f"{title} {desc}".lower()
        if re.search(r'\b(lead|principal|director|head of|vp|architect)\b', text):
            return "Lead / Principal"
        elif re.search(r'\b(senior|sr\.?|5\+|6\+|7\+|8\+ years?)\b', text):
            return "Senior Level"
        elif re.search(r'\b(entry|junior|jr\.?|associate|intern|fresher|graduate)\b', text):
            return "Entry Level"
        return "Mid-Level"

    @staticmethod
    def _infer_category(title: str, desc: str) -> str:
        text = f"{title} {desc}".lower()
        if re.search(r'\b(machine learning|ai|deep learning|data scientist|nlp|computer vision)\b', text):
            return "Data Science & AI"
        elif re.search(r'\b(cloud|devops|aws|kubernetes|infrastructure|sre)\b', text):
            return "Cloud & DevOps"
        elif re.search(r'\b(software|fullstack|backend|frontend|developer|engineer|python|react)\b', text):
            return "Software & Engineering"
        elif re.search(r'\b(product|project manager|agile|scrum)\b', text):
            return "Product Management"
        elif re.search(r'\b(hr|talent|recruiter|people)\b', text):
            return "Human Resources"
        elif re.search(r'\b(finance|accounting|controller|analyst)\b', text):
            return "Finance"
        return "Information Technology"
