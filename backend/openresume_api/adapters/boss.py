from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import random
import webbrowser

from sqlmodel import Session

from ..adapters.base import NormalizedJobDraft
from ..config import ROOT_DIR, settings
from ..models import CandidateProfile
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.browser_session import browser_session_service
from ..services.rules import rule_pack_service


class BossAdapter:
    platform = "boss"

    def __init__(self) -> None:
        fixtures_path = ROOT_DIR / "openresume_api" / "fixtures" / "boss_jobs.json"
        self.fixture_jobs = json.loads(fixtures_path.read_text(encoding="utf-8"))

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="Boss 直聘",
            search_supported=True,
            detail_parse_supported=True,
            review_open_supported=True,
            guided_apply_supported=True,
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        browser_session_service.start(db, self.platform, "https://www.zhipin.com/web/user/")

    async def session_state(self, db: Session) -> dict:
        return browser_session_service.state(db, self.platform)

    async def search_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
        wanted_targets = [value.lower() for value in search.job_targets or profile.target_roles]
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
            if wanted_targets and not any(target.lower() in haystack for target in wanted_targets):
                continue
            if wanted_cities and raw["city"] not in wanted_cities:
                continue

            await asyncio.sleep(random.uniform(0.08, 0.2))
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
        return results

    async def open_review(self, url: str) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        return "Opened listing in the default browser for manual review."

    async def guided_apply(self, url: str, profile: CandidateProfile) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        return (
            f"Opened dedicated listing flow for {profile.full_name or 'candidate'} and stopped before final submit."
        )


boss_adapter = BossAdapter()
