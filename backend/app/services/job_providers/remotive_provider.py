"""
Remotive Open API Provider for verified remote tech vacancies.
Official API Documentation: https://remotive.com/api/remote-jobs
"""
import html
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from app.ml.preprocessing import DEFAULT_SKILLS, extract_skills
from app.services.job_providers.base import (
    JobProvider,
    JobSearchQuery,
    LiveJobListing,
    ProviderSearchResult,
)

logger = logging.getLogger("inclusive_ats.job_providers.remotive")


class RemotiveJobProvider(JobProvider):
    name = "remotive"
    API_URL = "https://remotive.com/api/remote-jobs"

    def is_configured(self) -> bool:
        """Remotive API requires no API key and is always publicly available."""
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": "Remotive Open Jobs API",
            "name": self.name,
            "configured": True,
            "supports_indian_locations": False,  # Remote-only (Worldwide / India-remote)
            "official_documentation": "https://remotive.com/api/remote-jobs",
            "developer_portal": "https://remotive.com",
            "required_env_vars": [],
            "message": "Remotive Open API is active for worldwide verified remote tech roles (no API key required)."
        }

    def search(self, query: JobSearchQuery) -> ProviderSearchResult:
        # If user explicitly requested strictly on-site jobs, Remotive has no on-site jobs
        if query.work_arrangement == "on-site":
            return ProviderSearchResult(
                provider="Remotive Open Jobs API",
                status="success",
                message="Remotive exclusively indexes remote vacancies; none match on-site filter.",
                total=0,
                page=query.page,
                limit=query.limit,
                items=[]
            )

        # Sanitize search keywords
        raw_keywords = (query.keywords or "").strip()
        safe_keywords = re.sub(r'[^a-zA-Z0-9+#. ]', ' ', raw_keywords)
        safe_keywords = re.sub(r'\s+', ' ', safe_keywords).strip()

        params: Dict[str, Any] = {
            "limit": min(query.limit * 2, 50)
        }
        if safe_keywords:
            params["search"] = safe_keywords

        if query.category:
            cat_slug = self._map_category_to_slug(query.category)
            if cat_slug:
                params["category"] = cat_slug

        logger.info(f"Querying Remotive API: search='{safe_keywords}', category='{query.category}'")

        try:
            timeout_cfg = httpx.Timeout(timeout=6.0, connect=3.0)
            with httpx.Client(timeout=timeout_cfg) as client:
                resp = client.get(self.API_URL, params=params)

                if resp.status_code == 200:
                    data = resp.json()
                    raw_jobs = data.get("jobs", [])
                    listings = self._normalize_items(raw_jobs, query)

                    # Simple manual pagination over Remotive list
                    page = max(1, query.page)
                    start_idx = (page - 1) * query.limit
                    paged_items = listings[start_idx:start_idx + query.limit]

                    return ProviderSearchResult(
                        provider="Remotive Open Jobs API",
                        status="success",
                        message=(
                            f"Retrieved {len(paged_items)} remote vacancies from Remotive."
                            if paged_items
                            else f"No remote vacancies found matching '{safe_keywords}' on Remotive."
                        ),
                        total=len(listings),
                        page=page,
                        limit=query.limit,
                        items=paged_items
                    )

                elif resp.status_code == 429:
                    logger.warning("Remotive API rate limit reached (HTTP 429).")
                    return ProviderSearchResult(
                        provider="Remotive Open Jobs API",
                        status="rate_limited",
                        message="Remotive API rate limit reached. Please wait a moment before searching again.",
                        total=0,
                        page=query.page,
                        limit=query.limit,
                        items=[]
                    )
                else:
                    logger.warning(f"Remotive API responded with HTTP {resp.status_code}: {resp.text[:200]}")
                    return ProviderSearchResult(
                        provider="Remotive Open Jobs API",
                        status="error",
                        message=f"Remotive API returned HTTP {resp.status_code}.",
                        total=0,
                        page=query.page,
                        limit=query.limit,
                        items=[]
                    )

        except httpx.TimeoutException:
            logger.warning("Remotive API request timed out after 6.0 seconds.")
            return ProviderSearchResult(
                provider="Remotive Open Jobs API",
                status="error",
                message="Remotive API request timed out.",
                total=0,
                page=query.page,
                limit=query.limit,
                items=[]
            )
        except Exception as e:
            logger.error(f"Remotive API connection error: {e}", exc_info=True)
            return ProviderSearchResult(
                provider="Remotive Open Jobs API",
                status="error",
                message=f"Could not connect to Remotive API: {e}",
                total=0,
                page=query.page,
                limit=query.limit,
                items=[]
            )

    def _normalize_items(
        self,
        raw_items: List[Dict[str, Any]],
        query: JobSearchQuery
    ) -> List[LiveJobListing]:
        listings: List[LiveJobListing] = []

        for it in raw_items:
            raw_title = it.get("title", "").strip()
            title = html.unescape(re.sub(r'<[^>]+>', ' ', raw_title)).strip()
            company_name = it.get("company_name", "Remote Partner").strip()

            raw_desc = it.get("description", "")
            clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', raw_desc)).strip()
            if len(clean_desc) > 1200:
                clean_desc = clean_desc[:1200] + "…"

            candidate_location = (it.get("candidate_required_location") or "Worldwide (Remote)").strip()

            # Location filtering for Remotive
            if query.location and query.location.strip():
                req_loc = query.location.strip().lower()
                cand_lower = candidate_location.lower()
                # If specific location requested, keep only if worldwide, anywhere, or contains location
                is_compatible_location = (
                    "worldwide" in cand_lower or
                    "anywhere" in cand_lower or
                    req_loc in cand_lower or
                    ("india" in cand_lower and ("kolkata" in req_loc or "delhi" in req_loc or "india" in req_loc))
                )
                if not is_compatible_location:
                    continue

            # Publication date
            created_date = it.get("publication_date")
            if created_date and "T" in created_date:
                created_date = created_date.split("T")[0]

            job_id = f"remotive:{it.get('id', '')}"
            apply_url = it.get("url")

            # Skills from tags + text
            tags = it.get("tags") or []
            combined_text = f"{title} {' '.join(tags)} {clean_desc}".lower()
            matched_skills = sorted(list(extract_skills(combined_text, DEFAULT_SKILLS)))

            # Salary parsing if present
            salary_str = it.get("salary") or ""
            min_salary, max_salary, currency = self._parse_salary(salary_str)

            # Experience level
            experience_level = self._infer_experience_level(title, clean_desc)
            if query.experience_level and query.experience_level.lower() not in experience_level.lower():
                continue

            # Category
            category = it.get("category") or self._infer_category(title, clean_desc)

            listings.append(
                LiveJobListing(
                    source_id=job_id,
                    source_provider="remotive",
                    source_label="Live Vacancy (Remotive - Remote)",
                    title=title,
                    company_name=company_name,
                    description=clean_desc,
                    location=f"{candidate_location} (Remote)",
                    country=None,  # Remotive can be multi-country or worldwide
                    available_requirements=matched_skills[:8],
                    source_url=apply_url,
                    application_url=apply_url,
                    posting_date=created_date,
                    expiry_date=None,
                    min_salary=min_salary,
                    max_salary=max_salary,
                    salary_currency=currency,
                    job_type="remote",
                    experience_level=experience_level,
                    category=category,
                    is_live=True
                )
            )

        return listings

    @staticmethod
    def _parse_salary(salary_str: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
        if not salary_str:
            return None, None, None

        currency = "USD"
        if "€" in salary_str or "EUR" in salary_str:
            currency = "EUR"
        elif "£" in salary_str or "GBP" in salary_str:
            currency = "GBP"
        elif "₹" in salary_str or "INR" in salary_str:
            currency = "INR"

        nums = re.findall(r'(\d+(?:,\d{3})*(?:\.\d+)?)k?', salary_str.lower())
        parsed_vals: List[float] = []
        for n in nums:
            raw = n.replace(",", "")
            try:
                val = float(raw)
                if val < 500:  # e.g. "80k" -> 80 -> 80000
                    val *= 1000
                parsed_vals.append(val)
            except ValueError:
                continue

        min_sal = min(parsed_vals) if parsed_vals else None
        max_sal = max(parsed_vals) if len(parsed_vals) > 1 else min_sal
        return min_sal, max_sal, currency if parsed_vals else None

    @staticmethod
    def _map_category_to_slug(category: str) -> Optional[str]:
        cat_lower = category.lower()
        if "software" in cat_lower or "developer" in cat_lower or "engineering" in cat_lower:
            return "software-dev"
        elif "data" in cat_lower or "ai" in cat_lower or "machine learning" in cat_lower:
            return "data"
        elif "devops" in cat_lower or "cloud" in cat_lower or "sysadmin" in cat_lower:
            return "devops"
        elif "product" in cat_lower:
            return "product"
        elif "design" in cat_lower:
            return "design"
        elif "qa" in cat_lower or "test" in cat_lower:
            return "qa"
        return None

    @staticmethod
    def _infer_experience_level(title: str, desc: str) -> str:
        text = f"{title} {desc}".lower()
        if re.search(r'\b(lead|principal|director|head of|vp|architect)\b', text):
            return "Lead / Principal"
        elif re.search(r'\b(senior|sr\.?|5\+|6\+|7\+|8\+ years?)\b', text):
            return "Senior Level"
        elif re.search(r'\b(entry|junior|jr\.?|associate|intern|graduate)\b', text):
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
        return "Information Technology"
