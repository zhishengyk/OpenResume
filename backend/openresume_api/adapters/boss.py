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
            disabled_reason="当前版本未启用 Boss 直聘接入。",
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        raise RuntimeError("当前版本未启用 Boss 直聘。")

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
        raise PlatformDataError("当前版本未启用 Boss 直聘。")

    async def open_review(self, url: str) -> str:
        raise RuntimeError("当前版本不支持 Boss 页面查看。")

    async def guided_apply(
        self,
        job: JobListing,
        profile: CandidateProfile,
    ) -> GuidedApplyOutcome:
        raise RuntimeError("当前版本不支持 Boss 引导投递。")


boss_adapter = BossAdapter()
