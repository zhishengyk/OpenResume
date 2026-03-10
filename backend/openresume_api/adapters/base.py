from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlmodel import Session

from ..models import CandidateProfile, JobListing
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate


@dataclass
class NormalizedJobDraft:
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
    skills_extracted: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    apply_url: str = ""
    salary_raw: str = ""
    salary_min: int | None = None
    salary_max: int | None = None
    lang: str = "zh-CN"
    crawl_time: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuidedApplyOutcome:
    status: str
    message: str
    verification_url: str | None = None
    launch_url: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


class PlatformBlockedError(RuntimeError):
    """Raised when the upstream platform requires manual intervention."""

    def __init__(
        self,
        message: str,
        *,
        verification_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.verification_url = verification_url


class PlatformDataError(RuntimeError):
    """Raised when the upstream platform response is unusable."""


class PlatformAdapter(Protocol):
    platform: str

    def capability(self) -> PlatformCapabilityResponse: ...

    async def start_session(self, db: Session) -> None: ...

    async def session_state(self, db: Session) -> dict: ...

    async def search_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]: ...

    async def open_review(self, url: str) -> str: ...

    async def guided_apply(
        self,
        job: JobListing,
        profile: CandidateProfile,
    ) -> GuidedApplyOutcome: ...
