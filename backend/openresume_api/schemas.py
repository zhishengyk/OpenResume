from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    source_filename: str | None = None
    source_language: str = "zh-CN"
    updated_at: datetime | None = None


class PlatformCapabilityResponse(BaseModel):
    platform: str
    label: str
    search_supported: bool
    detail_parse_supported: bool
    review_open_supported: bool
    guided_apply_supported: bool
    rule_pack_version: str


class PlatformSessionResponse(BaseModel):
    platform: str
    active: bool
    last_started_at: datetime | None = None
    storage_dir: str
    recommended_account_notice: str


class RiskConsentCreate(BaseModel):
    consent_type: str
    platform: str | None = None
    version: str = "1.0.0"


class SearchSessionCreate(BaseModel):
    platform: str
    mode: str
    job_targets: list[str]
    cities: list[str]
    salary_floor: int = 0
    must_have_keywords: list[str] = Field(default_factory=list)


class SearchEventPayload(BaseModel):
    type: str
    session_id: str
    message: str
    timestamp: datetime
    payload: dict[str, Any] | None = None


class JobMatchResponse(BaseModel):
    id: str
    job_id: str
    platform: str
    external_job_id: str
    title: str
    company_name: str
    city: str
    salary_text: str
    experience_text: str
    degree_text: str
    work_mode: str
    url: str
    jd_excerpt: str
    rule_score: float
    llm_score: float | None
    final_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]
    llm_summary: str | None
    cached_llm: bool


class AppStateResponse(BaseModel):
    launch_disclaimer_required: bool
    guided_apply_consents: list[str]
    emergency_stop_active: bool


class RiskStatusResponse(BaseModel):
    platform: str
    emergency_stop_active: bool
    cooldown_until: datetime | None
    remaining_hourly: int
    remaining_daily: int
    recent_risk_events: int


class EmergencyStopRequest(BaseModel):
    active: bool
