from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlmodel import Session

from ..models import CandidateProfile
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
    jd_text: str
    jd_hash: str
    raw_payload: dict


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

    async def guided_apply(self, url: str, profile: CandidateProfile) -> str: ...
