from __future__ import annotations

import asyncio
import hashlib
import json
import random
import webbrowser

from sqlmodel import Session

from ..adapters.base import NormalizedJobDraft, PlatformDataError
from ..config import ROOT_DIR, settings
from ..models import CandidateProfile
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.rules import rule_pack_service


class DemoAdapter:
    platform = "demo"

    def __init__(self) -> None:
        fixtures_path = ROOT_DIR / "openresume_api" / "fixtures" / "demo_jobs.json"
        self.fixture_jobs = json.loads(fixtures_path.read_text(encoding="utf-8"))

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="Demo 模块",
            search_supported=True,
            detail_parse_supported=True,
            review_open_supported=True,
            guided_apply_supported=True,
            session_supported=False,
            session_required=False,
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        raise RuntimeError("当前模块不需要平台会话。")

    async def session_state(self, db: Session) -> dict:
        return {
            "active": False,
            "search_ready": True,
            "storage_dir": "",
            "last_started_at": None,
        }

    async def search_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
        wanted_targets = [
            value.lower() for value in search.job_targets or profile.target_roles
        ]
        wanted_cities = set(search.cities or profile.preferred_cities)
        results: list[NormalizedJobDraft] = []

        for raw in self.fixture_jobs:
            haystack = " ".join(
                [
                    raw["title"],
                    raw["company_name"],
                    raw["jd_text"],
                    " ".join(raw.get("tags", [])),
                ]
            ).lower()
            if wanted_targets and not any(
                target.lower() in haystack for target in wanted_targets
            ):
                continue
            if wanted_cities and raw["city"] not in wanted_cities:
                continue

            await asyncio.sleep(random.uniform(0.01, 0.03))
            jd_hash = hashlib.md5(raw["jd_text"].encode("utf-8")).hexdigest()
            results.append(
                NormalizedJobDraft(
                    external_job_id=raw["id"],
                    title=raw["title"],
                    company_name=raw["company_name"],
                    city=raw["city"],
                    salary_text=raw["salary_text"],
                    salary_min=raw["salary_min"],
                    salary_max=raw["salary_max"],
                    experience_text=raw["experience_text"],
                    degree_text=raw["degree_text"],
                    work_mode=raw["work_mode"],
                    url=raw["url"],
                    jd_text=raw["jd_text"],
                    jd_hash=jd_hash,
                    raw_payload=raw,
                )
            )

        if not results:
            raise PlatformDataError("Demo 模块没有返回匹配的职位。")

        return results

    async def open_review(self, url: str) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        return "已打开演示职位链接。"

    async def guided_apply(self, url: str, profile: CandidateProfile) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        candidate_name = profile.full_name or "候选人"
        return (
            f"已为 {candidate_name} 准备演示投递流程。"
            "主分支不会驱动真实平台提交。"
        )


demo_adapter = DemoAdapter()
