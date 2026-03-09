from __future__ import annotations

from sqlmodel import Session

from ..models import CandidateProfile
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.rules import rule_pack_service


class LiepinAdapter:
    platform = "liepin"

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="猎聘模块",
            search_supported=False,
            detail_parse_supported=False,
            review_open_supported=False,
            guided_apply_supported=False,
            session_supported=False,
            session_required=False,
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        raise RuntimeError("猎聘模块暂未启用平台会话。")

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
        return []

    async def open_review(self, url: str) -> str:
        raise RuntimeError("猎聘模块暂未开放职位浏览。")

    async def guided_apply(self, url: str, profile: CandidateProfile) -> str:
        raise RuntimeError("猎聘模块暂未开放引导投递。")


liepin_adapter = LiepinAdapter()
