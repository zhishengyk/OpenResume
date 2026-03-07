from __future__ import annotations

from sqlmodel import Session

from ..models import CandidateProfile
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate


class LiepinAdapter:
    platform = "liepin"

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="猎聘",
            search_supported=False,
            detail_parse_supported=False,
            review_open_supported=False,
            guided_apply_supported=False,
            rule_pack_version="planned",
        )

    async def start_session(self, db: Session) -> None:
        return None

    async def session_state(self, db: Session) -> dict:
        return {"active": False, "storage_dir": "", "last_started_at": None}

    async def search_jobs(self, search: SearchSessionCreate, profile: CandidateProfile) -> list:
        return []

    async def open_review(self, url: str) -> str:
        raise NotImplementedError

    async def guided_apply(self, url: str, profile: CandidateProfile) -> str:
        raise NotImplementedError


liepin_adapter = LiepinAdapter()

