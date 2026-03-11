from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CandidateProfile(SQLModel, table=True):
    id: int | None = Field(default=1, primary_key=True)
    full_name: str = ""
    headline: str = ""
    summary: str = ""
    target_roles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    preferred_cities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    salary_floor: int = 0
    years_experience: int = 0
    degree: str = ""
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    must_have_keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    tech_stack: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    project_experiences: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )
    awards: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    source_filename: str | None = None
    source_language: str = "zh-CN"
    raw_text: str = ""
    updated_at: datetime = Field(default_factory=now_utc)


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=now_utc)


class SearchSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    requested_platforms: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )
    mode: str
    status: str = "draft"
    job_targets: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    cities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    salary_floor: int = 0
    must_have_keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    source_variants: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    source_companies: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    force_refresh: bool = False
    blocked_reason: str | None = None
    summary: str | None = None
    analysis_provider: str = "heuristic"
    analysis_degraded: bool = False
    analysis_notice: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class JobListing(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(index=True)
    platform: str
    source_company: str
    source_site: str
    job_id: str
    title: str
    department: str = ""
    employment_type: str = ""
    location_raw: str = ""
    location_city: str = ""
    location_country: str = ""
    remote_type: str = "unknown"
    description_html: str = ""
    description_text: str = ""
    requirements_text: str = ""
    skills_extracted: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    posted_at: datetime | None = None
    apply_url: str = ""
    salary_raw: str = ""
    salary_min: int | None = None
    salary_max: int | None = None
    lang: str = "zh-CN"
    crawl_time: datetime = Field(default_factory=now_utc)
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc)


class JobMatch(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(index=True)
    job_id: str = Field(index=True)
    rule_score: float
    llm_score: float | None = None
    final_score: float
    highlights: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    missing_keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    risk_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    llm_summary: str | None = None
    cached_llm: bool = False
    analysis_provider: str = "heuristic"
    analysis_degraded: bool = False
    analysis_notice: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ApplicationAttempt(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: str = Field(index=True)
    platform: str
    mode: str
    status: str = "queued"
    message: str = ""
    verification_url: str | None = None
    launch_url: str | None = None
    context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class RiskConsent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    consent_type: str = Field(index=True)
    platform: str | None = Field(default=None, index=True)
    version: str = "1.0.0"
    accepted_at: datetime = Field(default_factory=now_utc)


class RiskEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    platform: str = Field(index=True)
    event_type: str = Field(index=True)
    detail: str = ""
    created_at: datetime = Field(default_factory=now_utc)


class LLMAnalysisCache(SQLModel, table=True):
    cache_key: str = Field(primary_key=True)
    provider: str = "heuristic"
    platform: str
    source_site: str
    job_id: str
    content_hash: str
    llm_score: float
    highlights: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    missing_keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    risk_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    llm_summary: str = ""
    updated_at: datetime = Field(default_factory=now_utc)


class SearchFetchCache(SQLModel, table=True):
    cache_key: str = Field(primary_key=True)
    platforms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    source_filters: dict[str, list[str]] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
    )
    keyword_basis: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    payload_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc)
    expires_at: datetime = Field(default_factory=now_utc)
    hit_count: int = 0
