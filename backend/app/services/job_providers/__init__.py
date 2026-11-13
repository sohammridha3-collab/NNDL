"""
Job Providers Package.
Standardized interfaces, schemas, and implementations for authorized external job retrieval.
"""
from app.services.job_providers.base import (
    JobProvider,
    JobSearchQuery,
    LiveJobListing,
    ProviderSearchResult,
)
from app.services.job_providers.adzuna_provider import (
    AdzunaJobProvider,
    INDIAN_LOCATIONS,
    SUPPORTED_ADZUNA_COUNTRIES,
)
from app.services.job_providers.remotive_provider import RemotiveJobProvider
from app.services.job_providers.registry import JobProviderRegistry, registry

__all__ = [
    "JobProvider",
    "JobSearchQuery",
    "LiveJobListing",
    "ProviderSearchResult",
    "AdzunaJobProvider",
    "RemotiveJobProvider",
    "JobProviderRegistry",
    "registry",
    "INDIAN_LOCATIONS",
    "SUPPORTED_ADZUNA_COUNTRIES",
]
