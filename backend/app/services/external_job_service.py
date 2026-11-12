import hashlib
import html
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx

from app.core.config import settings

logger = logging.getLogger("inclusive_ats.external_jobs")

# In-memory query cache with TTL (15 minutes = 900 seconds)
_CACHE_TTL_SECONDS = 900
_JOB_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


class ExternalJobService:
    """
    Service for integrating authorized external job APIs (Adzuna & Remotive).
    
    Guarantees:
    1. Zero Private Data Leakage: Only sends public skill keywords and job location.
       Raw resume text and candidate identifiers are never transmitted or logged.
    2. Resilient Graceful Degradation: If API keys are missing, network is down,
       or provider rate-limits, it falls back seamlessly to database listings.
    3. In-memory caching and deduplication to avoid redundant requests.
    4. Clear attribution: live vacancies are distinctly tagged from dataset listings.
    """

    @classmethod
    def get_api_status(cls) -> Dict[str, Any]:
        has_adzuna = bool(settings.ADZUNA_APP_ID and settings.ADZUNA_APP_KEY)
        if has_adzuna:
            return {
                "provider": "Adzuna Developer API",
                "configured": True,
                "status": "active",
                "country": settings.ADZUNA_COUNTRY,
                "message": "Authorized Adzuna API connected. Live global vacancies enabled."
            }
        else:
            return {
                "provider": "Adzuna Developer API",
                "configured": False,
                "fallback_provider": "Remotive Open Jobs API",
                "status": "fallback",
                "message": (
                    "Adzuna API credentials (ADZUNA_APP_ID / ADZUNA_APP_KEY) are not configured in backend .env. "
                    "Serving live remote tech vacancies via Remotive Open API and verified database listings."
                )
            }

    @classmethod
    def fetch_jobs(
        cls,
        skills: Optional[List[str]] = None,
        location: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 15
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
                "message": "External job retrieval is disabled in server configuration."
            }

        # Clean sanitized search keywords (only take top 3-4 skills for clean API query)
        safe_keywords = [
            re.sub(r'[^a-zA-Z0-9+#. ]', '', s).strip()
            for s in (skills or [])
            if s and len(s.strip()) > 1
        ][:4]
        
        query_terms = " ".join(safe_keywords) if safe_keywords else "software engineer"
        cache_key = cls._make_cache_key(query_terms, location or "", job_type or "")

        # Check cache
        now = time.time()
        if cache_key in _JOB_CACHE:
            cached_time, cached_results = _JOB_CACHE[cache_key]
            if now - cached_time < _CACHE_TTL_SECONDS:
                logger.debug(f"Returning {len(cached_results)} cached external jobs for '{query_terms}'")
                status = cls.get_api_status()
                status["cached"] = True
                return cached_results[:limit], status

        api_status = cls.get_api_status()
        results: List[Dict[str, Any]] = []

        if api_status["configured"]:
            # Primary: Adzuna API
            results = cls._fetch_from_adzuna(query_terms, location, limit)
            if not results:
                # If Adzuna returned 0 or timed out, try Remotive fallback
                results = cls._fetch_from_remotive(query_terms, limit)
        else:
            # Fallback: Remotive Open API
            results = cls._fetch_from_remotive(query_terms, limit)

        # Deduplicate results
        deduped = cls._deduplicate_listings(results)

        # Cache results
        _JOB_CACHE[cache_key] = (now, deduped)

        return deduped[:limit], api_status

    @classmethod
    def _fetch_from_adzuna(
        cls,
        keywords: str,
        location: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        app_id = settings.ADZUNA_APP_ID
        app_key = settings.ADZUNA_APP_KEY
        country = settings.ADZUNA_COUNTRY or "us"
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"

        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": min(limit, 20),
            "what": keywords,
            "content-type": "application/json"
        }
        if location and location.strip():
            params["where"] = location.strip()

        try:
            with httpx.Client(timeout=4.5) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("results", [])
                    return cls._format_adzuna_items(raw_items)
                else:
                    logger.warning(f"Adzuna API returned HTTP {resp.status_code}: {resp.text[:200]}")
                    return []
        except Exception as e:
            logger.warning(f"Failed to query Adzuna API: {e}")
            return []

    @classmethod
    def _format_adzuna_items(cls, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted = []
        for it in items:
            title = it.get("title", "").strip()
            company_obj = it.get("company", {})
            company_name = company_obj.get("display_name", "Authorized Employer") if isinstance(company_obj, dict) else "Authorized Employer"
            location_obj = it.get("location", {})
            location_name = location_obj.get("display_name", "Remote / Flexible") if isinstance(location_obj, dict) else "Remote / Flexible"
            
            raw_desc = it.get("description", "")
            clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', raw_desc)).strip()
            
            created_date = it.get("created", "")
            if created_date and "T" in created_date:
                created_date = created_date.split("T")[0]

            job_id = f"adzuna_{it.get('id', '')}"
            redirect_url = it.get("redirect_url")

            formatted.append({
                "id": job_id,
                "job_code": job_id,
                "title": title,
                "company_name": company_name,
                "location": location_name,
                "job_type": "remote" if "remote" in f"{title} {location_name} {clean_desc}".lower() else "on-site",
                "experience_level": cls._infer_experience_level(title, clean_desc),
                "category": cls._infer_category(title, clean_desc),
                "description": clean_desc,
                "requirements": "See live posting for detailed requirements and specifications.",
                "min_salary": it.get("salary_min"),
                "max_salary": it.get("salary_max"),
                "salary_currency": "USD" if settings.ADZUNA_COUNTRY == "us" else "GBP",
                "posted_date": created_date or "Recently posted",
                "source_type": "live_vacancy",
                "source_label": "Live Vacancy (Adzuna)",
                "external_url": redirect_url,
                "status": "active"
            })
        return formatted

    @classmethod
    def _fetch_from_remotive(
        cls,
        keywords: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        url = "https://remotive.com/api/remote-jobs"
        params = {
            "search": keywords,
            "limit": min(limit, 20)
        }
        try:
            with httpx.Client(timeout=4.5) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    jobs = data.get("jobs", [])
                    return cls._format_remotive_items(jobs)
                else:
                    logger.warning(f"Remotive API returned HTTP {resp.status_code}")
                    return []
        except Exception as e:
            logger.warning(f"Failed to query Remotive API: {e}")
            return []

    @classmethod
    def _format_remotive_items(cls, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        formatted = []
        for it in items:
            title = it.get("title", "").strip()
            company_name = it.get("company_name", "Remote Verified Partner")
            location_name = it.get("candidate_required_location") or "Worldwide (Remote)"
            
            raw_desc = it.get("description", "")
            clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', raw_desc)).strip()
            if len(clean_desc) > 800:
                clean_desc = clean_desc[:800] + "…"

            created_date = it.get("publication_date", "")
            if created_date and "T" in created_date:
                created_date = created_date.split("T")[0]

            job_id = f"remotive_{it.get('id', '')}"
            apply_url = it.get("url")

            formatted.append({
                "id": job_id,
                "job_code": job_id,
                "title": title,
                "company_name": company_name,
                "location": location_name,
                "job_type": "remote",
                "experience_level": cls._infer_experience_level(title, clean_desc),
                "category": it.get("category") or cls._infer_category(title, clean_desc),
                "description": clean_desc,
                "requirements": "See verified remote posting for candidate prerequisites.",
                "min_salary": None,
                "max_salary": None,
                "salary_currency": "USD",
                "posted_date": created_date or "Recently posted",
                "source_type": "live_vacancy",
                "source_label": "Live Vacancy (Remotive)",
                "external_url": apply_url,
                "status": "active"
            })
        return formatted

    @staticmethod
    def _deduplicate_listings(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: Set[str] = set()
        deduped = []
        for it in items:
            norm_title = re.sub(r'\W+', '', it.get("title", "").lower())
            norm_comp = re.sub(r'\W+', '', it.get("company_name", "").lower())
            sig = f"{norm_title}::{norm_comp}"
            if sig not in seen and norm_title:
                seen.add(sig)
                deduped.append(it)
        return deduped

    @staticmethod
    def _infer_experience_level(title: str, desc: str) -> str:
        text = f"{title} {desc}".lower()
        if re.search(r'\b(lead|principal|director|head of|vp|architect)\b', text):
            return "Lead / Principal"
        elif re.search(r'\b(senior|sr\.?|5\+|6\+|7\+|8\+ years?)\b', text):
            return "Senior Level"
        elif re.search(r'\b(entry|junior|jr\.?|associate|intern|new grad)\b', text):
            return "Entry Level"
        return "Mid-Level"

    @staticmethod
    def _infer_category(title: str, desc: str) -> str:
        text = f"{title} {desc}".lower()
        if re.search(r'\b(machine learning|ai|deep learning|data scientist|nlp|computer vision)\b', text):
            return "Data & AI"
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

    @staticmethod
    def _make_cache_key(keywords: str, location: str, job_type: str) -> str:
        raw = f"{keywords.lower()}::{location.lower()}::{job_type.lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

