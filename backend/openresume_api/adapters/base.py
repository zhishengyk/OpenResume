from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlmodel import Session

from ..models import CandidateProfile, JobListing
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate


@dataclass
class NormalizedJobDraft:
    external_job_id: str
    title: str
    company_name: str
    city: str
    salary_text: str
    salary_min: int
    salary_max: int
    experience_text: str
    degree_text: str
    work_mode: str
    url: str
    detail_url: str | None = None
    apply_url: str | None = None
    source_company_url: str | None = None
    apply_requires_login: bool = False
    jd_text: str = ""
    jd_hash: str = ""
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
