from __future__ import annotations

from sqlmodel import Session

from ..models import CandidateProfile, JobListing
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.rules import rule_pack_service
from .base import GuidedApplyOutcome, PlatformDataError


class BossAdapter:
    platform = "boss"

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="Boss",
            search_supported=False,
            detail_parse_supported=False,
            review_open_supported=False,
            guided_apply_supported=False,
            session_supported=False,
            session_required=False,
            selectable=False,
            disabled_reason="Boss integration is parked on archive/boss-login.",
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        raise RuntimeError("Boss is disabled on the main branch.")

    async def session_state(self, db: Session) -> dict:
        return {
            "active": False,
            "search_ready": False,
            "storage_dir": "",
            "last_started_at": None,
        }

    async def search_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list:
        raise PlatformDataError("Boss is disabled on the main branch.")

    async def open_review(self, url: str) -> str:
        raise RuntimeError("Boss review is not available on the main branch.")

    async def guided_apply(
        self,
        job: JobListing,
        profile: CandidateProfile,
    ) -> GuidedApplyOutcome:
        raise RuntimeError("Boss guided apply is not available on the main branch.")


boss_adapter = BossAdapter()
