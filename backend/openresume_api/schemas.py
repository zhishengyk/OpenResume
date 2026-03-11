from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProjectExperienceItem(BaseModel):
    name: str = ""
    role: str = ""
    summary: str = ""
    technologies: list[str] = Field(default_factory=list)


class AwardItem(BaseModel):
    title: str = ""
    issuer: str = ""
    year: str = ""
    summary: str = ""


class CandidateProfileUpdate(BaseModel):
    id: int | None = 1
    full_name: str = ""
    headline: str = ""
    summary: str = ""
    target_roles: list[str] = Field(default_factory=list)
    preferred_cities: list[str] = Field(default_factory=list)
    salary_floor: int = 0
    years_experience: int = 0
    degree: str = ""
    skills: list[str] = Field(default_factory=list)
    must_have_keywords: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    project_experiences: list[ProjectExperienceItem] = Field(default_factory=list)
    awards: list[AwardItem] = Field(default_factory=list)
    source_filename: str | None = None
    source_language: str = "zh-CN"
    raw_text: str = ""
    updated_at: datetime | None = None


class PlatformCapabilityResponse(BaseModel):
    platform: str
    label: str
    search_supported: bool
    detail_parse_supported: bool
    review_open_supported: bool
    guided_apply_supported: bool
    session_supported: bool = False
    session_required: bool = False
    selectable: bool = True
    disabled_reason: str | None = None
    rule_pack_version: str


class PlatformSessionResponse(BaseModel):
    platform: str
    active: bool
    search_ready: bool = False
    last_started_at: datetime | None = None
    storage_dir: str
    recommended_account_notice: str


class RiskConsentCreate(BaseModel):
    consent_type: str
    platform: str | None = None
    version: str = "1.0.0"


class SearchSessionCreate(BaseModel):
    platforms: list[str] = Field(default_factory=list)
    mode: str
    job_targets: list[str]
    cities: list[str]
    salary_floor: int = 0
    must_have_keywords: list[str] = Field(default_factory=list)
    source_variants: list[str] = Field(default_factory=list)
    source_companies: list[str] = Field(default_factory=list)
    match_limit: int = Field(default=200, ge=1, le=1000)
    company_job_limit: int = Field(default=200, ge=1, le=1000)
    force_refresh: bool = False


class SearchEventPayload(BaseModel):
    type: str
    session_id: str
    message: str
    timestamp: datetime
    payload: dict[str, Any] | None = None


class JobLocationOptionResponse(BaseModel):
    listing_id: str
    location_city: str
    location_raw: str
    apply_url: str


class SearchSessionResponse(BaseModel):
    id: str
    requested_platforms: list[str]
    mode: str
    status: str
    job_targets: list[str]
    cities: list[str]
    salary_floor: int
    must_have_keywords: list[str]
    source_variants: list[str]
    source_companies: list[str]
    match_limit: int
    company_job_limit: int
    force_refresh: bool
    blocked_reason: str | None
    summary: str | None
    analysis_status: str
    analysis_provider: str
    analysis_degraded: bool
    analysis_notice: str | None
    created_at: datetime
    updated_at: datetime


class JobMatchResponse(BaseModel):
    id: str
    listing_id: str
    platform: str
    job_id: str
    source_company: str
    source_site: str
    title: str
    department: str
    employment_type: str
    location_raw: str
    location_city: str
    location_country: str
    remote_type: str
    description_html: str
    description_text: str
    requirements_text: str
    skills_extracted: list[str]
    posted_at: datetime | None
    apply_url: str
    location_display: str
    location_cities: list[str]
    location_options: list[JobLocationOptionResponse]
    is_merged: bool
    merged_count: int
    salary_raw: str
    salary_min: int | None
    salary_max: int | None
    lang: str
    crawl_time: datetime
    apply_supported: bool
    rule_score: float
    llm_score: float | None
    final_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]
    llm_summary: str | None
    cached_llm: bool
    analysis_provider: str
    analysis_degraded: bool
    analysis_notice: str | None


class VerificationWindowResponse(BaseModel):
    url: str
    title: str
    message: str


class ApplicationAttemptResponse(BaseModel):
    id: str
    listing_id: str
    platform: str
    mode: str
    status: str
    created_at: datetime
    updated_at: datetime
    message: str
    verification_url: str | None = None
    launch_url: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AppStateResponse(BaseModel):
    launch_disclaimer_required: bool
    guided_apply_consents: list[str]
    emergency_stop_active: bool


class RuntimeConfigResponse(BaseModel):
    api_port: int
    llm_provider: str
    llm_effective_provider: str
    llm_configured: bool
    llm_missing_envs: list[str]
    llm_notice: str
    openai_api_key_configured: bool
    openai_api_key_preview: str | None
    openai_base_url: str | None
    openai_model: str | None
    official_sources_summary: str


class RuntimeConfigUpdateRequest(BaseModel):
    llm_provider: str = "heuristic"
    openai_base_url: str | None = None
    openai_model: str | None = None
    openai_api_key: str | None = None
    replace_api_key: bool = False


class LLMRuntimeProbeRequest(BaseModel):
    llm_provider: str = "openai_compatible"
    openai_base_url: str | None = None
    openai_model: str | None = None
    openai_api_key: str | None = None
    use_saved_api_key: bool = True


class LLMConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str | None
    latency_ms: int | None = None
    reply_preview: str | None = None
    message: str


class LLMModelListResponse(BaseModel):
    provider: str
    models: list[str]
    message: str


class RiskStatusResponse(BaseModel):
    platform: str
    emergency_stop_active: bool
    cooldown_until: datetime | None
    remaining_hourly: int
    remaining_daily: int
    recent_risk_events: int


class EmergencyStopRequest(BaseModel):
    active: bool
