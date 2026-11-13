"""
Base abstractions and standardized schemas for external live job retrieval providers.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobSearchQuery(BaseModel):
    """
    Standardized query parameters across all live job search providers.
    """
    keywords: Optional[str] = None
    location: Optional[str] = None  # e.g. "Kolkata", "Delhi", "Bengaluru", "Remote"
    country: str = "in"  # Default to India ('in') for Indian job search
    work_arrangement: Optional[str] = None  # "remote", "hybrid", "on-site", "all"
    experience_level: Optional[str] = None  # "Entry Level", "Mid-Level", "Senior Level", "Lead / Principal"
    category: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=12, ge=1, le=50)
    max_days_old: Optional[int] = Field(default=30, ge=1, le=365)


class LiveJobListing(BaseModel):
    """
    Normalized shared schema for live external vacancies.
    Explicitly marked with is_live=True so training CSV / dataset records never masquerade as live.
    Preserves unknown values as None.
    """
    source_id: str
    source_provider: str  # "adzuna", "remotive", etc.
    source_label: str  # e.g. "Live Vacancy (Adzuna - India)", "Live Vacancy (Remotive)"
    title: str
    company_name: str
    description: str
    location: str
    country: Optional[str] = None
    available_requirements: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    application_url: Optional[str] = None
    posting_date: Optional[str] = None
    expiry_date: Optional[str] = None
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    salary_currency: Optional[str] = None
    job_type: str = "on-site"  # "remote", "hybrid", "on-site"
    experience_level: Optional[str] = None
    category: Optional[str] = None
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_live: bool = True


class ProviderSearchResult(BaseModel):
    """
    Standardized result contract returned by any job provider.
    Distinguishes unconfigured, rate-limited, empty success, and error states.
    """
    provider: str
    status: str  # "success" | "unconfigured" | "rate_limited" | "error"
    message: str
    total: int = 0
    page: int = 1
    limit: int = 12
    items: List[LiveJobListing] = Field(default_factory=list)
    cached: bool = False


class JobProvider(ABC):
    """
    Extensible abstract interface for live job search providers.
    Allows seamlessly connecting Adzuna, Remotive, or additional employer feeds.
    """
    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if required environment variables / credentials are set."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns provider connectivity, credential status, and documentation."""
        pass

    @abstractmethod
    def search(self, query: JobSearchQuery) -> ProviderSearchResult:
        """Executes a bounded live vacancy search conforming to query filters."""
        pass
