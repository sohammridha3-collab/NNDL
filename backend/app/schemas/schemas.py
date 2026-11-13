from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ==========================================
# AUTH SCHEMAS
# ==========================================
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    full_name: str = Field(..., min_length=2)
    role: str = Field(default="candidate", pattern="^(candidate|recruiter|admin)$")
    company_name: Optional[str] = None  # If registering as recruiter


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# PROFILE & COMPANY SCHEMAS
# ==========================================
class CandidateProfileUpdate(BaseModel):
    phone: Optional[str] = None
    location: Optional[str] = None
    target_title: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None
    years_experience: Optional[float] = None


class RecruiterProfileUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None


class CompanyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None


class CompanyResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# RESUME SCHEMAS
# ==========================================
class SkillItem(BaseModel):
    name: str
    category: Optional[str] = "technical"
    confidence: float = 1.0


class ResumeResponse(BaseModel):
    id: str
    user_id: str
    file_name: str
    file_type: str
    file_size_bytes: int
    version: int
    is_active: bool
    ats_score: float
    completeness_score: float
    skills: List[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResumeAnalysisResponse(BaseModel):
    resume_id: str
    ats_score: float
    completeness_score: float
    readability_rating: str
    extracted_skills: List[str]
    identified_sections: List[str]
    missing_critical_sections: List[str]
    strengths: List[str]
    improvement_recommendations: List[str]
    sdg10_bias_mitigation_applied: bool


# ==========================================
# JOB SCHEMAS
# ==========================================
class JobCreate(BaseModel):
    title: str = Field(..., min_length=3)
    category: Optional[str] = "Software & Technology"
    description: str = Field(..., min_length=20)
    requirements: Optional[str] = None
    location: str = "Remote"
    job_type: str = Field(default="remote", pattern="^(remote|hybrid|on-site)$")
    experience_level: str = "Mid-Level"
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    salary_currency: str = "USD"
    skills: List[str] = []


class JobUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    experience_level: Optional[str] = None
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    status: Optional[str] = None
    skills: Optional[List[str]] = None


class JobResponse(BaseModel):
    id: str
    job_code: Optional[str] = None
    title: str
    category: Optional[str] = None
    description: str
    requirements: Optional[str] = None
    location: str
    job_type: str
    experience_level: str
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    salary_currency: str = "USD"
    status: str
    company_name: Optional[str] = "Verified Tech Partner"
    skills: List[str] = []
    applicant_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# APPLICATION SCHEMAS
# ==========================================
class ApplicationCreate(BaseModel):
    resume_id: Optional[str] = None
    cover_note: Optional[str] = None


class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    stage: Optional[str] = None
    recruiter_note: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: str
    job_id: str
    candidate_id: str
    resume_id: Optional[str] = None
    candidate_name: str
    candidate_email: str
    job_title: str
    company_name: Optional[str] = None
    status: str
    stage: str
    match_score: Optional[float] = None
    cover_note: Optional[str] = None
    recruiter_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# AI MATCHING & RECOMMENDATION SCHEMAS
# ==========================================
class MatchingRequest(BaseModel):
    resume_id: Optional[str] = None
    job_id: Optional[str] = None
    resume_text: Optional[str] = None
    job_text: Optional[str] = None


class BatchMatchingRequest(BaseModel):
    job_id: str
    resume_ids: List[str]


class MatchingResponse(BaseModel):
    candidate_id: Optional[str] = None
    job_id: Optional[str] = None
    # compatibility_score is the classifier's sigmoid probability expressed on a 0-100 scale.
    # decision_threshold is expressed on the 0-1 probability scale.
    compatibility_score: float
    score_type: str = "model_probability_percent"
    classification: str
    decision_threshold: float
    semantic_similarity: float
    required_skill_coverage: float
    matched_skills: List[str]
    missing_skills: List[str]
    requirements_breakdown: Optional[Dict[str, Any]] = None
    learning_checklist: Optional[List[Dict[str, Any]]] = None
    recommendations: List[str]
    disclaimer: Optional[str] = (
        "This score estimates résumé–job compatibility according to the model’s training labels. "
        "It is not the probability of being hired."
    )
    explanation: Dict[str, Any]
    model_version: str = "MiniLM + PyTorch MLP v1.0"
    # Optional metadata, populated for persisted history records
    id: Optional[str] = None
    resume_id: Optional[str] = None
    job_title: Optional[str] = None
    created_at: Optional[datetime] = None


# ==========================================
# SKILL EXTRACTION & SKILL-BASED RECOMMENDATION SCHEMAS
# ==========================================
class SkillExtractionRequest(BaseModel):
    resume_id: Optional[str] = None
    resume_text: Optional[str] = None
    text: Optional[str] = None


class SkillExtractionResponse(BaseModel):
    skills: List[str]
    source: str
    count: int


# ==========================================
# RESUME PROFILE SUMMARY SCHEMAS
# ==========================================
class EmploymentHistoryItem(BaseModel):
    title: str
    company: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_months: int = 0
    description: Optional[str] = None


class ResumeProfileSummaryRequest(BaseModel):
    resume_id: Optional[str] = None
    resume_text: Optional[str] = None


class ResumeProfileSummaryResponse(BaseModel):
    readable: bool = True
    is_scanned: bool = False
    recovery_needed: bool = False
    recovery_message: Optional[str] = None
    raw_text: str = ""
    summary: Optional[str] = None
    primary_role: Optional[str] = None
    detected_titles: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    total_experience_years: float = 0.0
    employment_history: List[EmploymentHistoryItem] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    detected_location: Optional[str] = None


class JobRecommendationItem(BaseModel):
    id: Optional[str] = None
    job_code: Optional[str] = None
    title: str
    company_name: str
    location: str
    job_type: str  # remote, hybrid, on-site
    experience_level: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    salary_currency: Optional[str] = "USD"
    posted_date: Optional[str] = None
    source_type: str  # "curated_dataset" or "live_vacancy"
    source_label: str  # "Curated Dataset Listing" or "Live Vacancy (Adzuna)"
    external_url: Optional[str] = None
    source_url: Optional[str] = None
    application_url: Optional[str] = None
    retrieved_at: Optional[str] = None
    is_cached: bool = False
    freshness_label: str = "Retrieved recently"
    score: float  # 0 to 100
    score_type: str  # "skills_only_relevance" or "model_probability_percent" or "unranked_sparse_description"
    score_label: str  # "Skills-Only Relevance" or "AI Résumé-Job Match Fit"
    classification: Optional[str] = None
    semantic_similarity: float
    skill_coverage: float
    matched_skills: List[str]
    missing_skills: List[str]
    experience_requirements: Optional[str] = None
    qualification_breakdown: Optional[Dict[str, List[str]]] = None
    relevance_explanation: str
    disclaimer: str = "This score estimates résumé–job compatibility according to the model’s training labels. It is not the probability of being hired."
    is_saved: bool = False


class SkillRecommendationRequest(BaseModel):
    skills: List[str] = Field(default_factory=list)
    preferred_titles: List[str] = Field(default_factory=list)
    resume_id: Optional[str] = None
    resume_text: Optional[str] = None
    category: Optional[str] = None
    job_type: Optional[str] = None
    location: Optional[str] = None
    country: str = "in"
    experience_level: Optional[str] = None
    min_salary: Optional[float] = None
    limit: int = Field(default=12, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    include_external: bool = True


class SkillRecommendationResponse(BaseModel):
    total: int
    page: int
    limit: int
    active_skills: List[str]
    has_resume_context: bool
    api_status: Dict[str, Any]
    items: List[JobRecommendationItem]
    empty_reason: Optional[str] = None
    broadening_suggestions: List[str] = Field(default_factory=list)
    queries_executed: List[str] = Field(default_factory=list)



# ==========================================
# DASHBOARD SCHEMAS
# ==========================================
class CandidateDashboardResponse(BaseModel):
    active_resume: Optional[ResumeResponse] = None
    total_applications: int
    applications: List[Dict[str, Any]]
    saved_jobs_count: int
    top_recommended_jobs: List[Dict[str, Any]]
    profile_completion: float
    recent_activity: List[Dict[str, Any]]


class RecruiterDashboardResponse(BaseModel):
    total_active_jobs: int
    total_applicants: int
    recent_jobs: List[Dict[str, Any]]
    recent_applicants: List[Dict[str, Any]]
    pipeline_stages_count: Dict[str, int]
    hiring_trends: List[Dict[str, Any]]


class AdminDashboardResponse(BaseModel):
    total_users: int
    total_candidates: int
    total_recruiters: int
    total_jobs: int
    total_applications: int
    total_matches_run: int
    fairness_summary: Dict[str, Any]
    system_health: Dict[str, Any]


# ==========================================
# FAIRNESS AUDIT SCHEMAS (SDG 10)
# ==========================================
class FairnessAuditRequest(BaseModel):
    name: Optional[str] = "SDG 10 Counterfactual Fairness Audit"
    attributes: List[str] = ["name", "pronoun", "age"]


class FairnessAuditResponse(BaseModel):
    audit_id: str
    name: str
    model_version: str
    timestamp: datetime
    demographic_parity_summary: Dict[str, Any]
    counterfactual_sensitivity_results: List[Dict[str, Any]]
    overall_fairness_verdict: str
    recommendations: List[str]


# ==========================================
# LIVE EXTERNAL JOB PROVIDER SCHEMAS
# ==========================================
class LiveJobListingResponse(BaseModel):
    source_id: str
    source_provider: str
    source_label: str
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
    job_type: str = "on-site"
    experience_level: Optional[str] = None
    category: Optional[str] = None
    retrieval_timestamp: Optional[str] = None
    is_live: bool = True


class LiveJobSearchResponse(BaseModel):
    provider: str
    status: str
    message: str
    total: int = 0
    page: int = 1
    limit: int = 12
    items: List[LiveJobListingResponse] = Field(default_factory=list)
    cached: bool = False

