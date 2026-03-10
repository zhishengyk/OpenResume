from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from ..config import settings
from ..models import CandidateProfile, now_utc
from ..schemas import SearchSessionCreate
from .base import CareerSiteSource, CollectorRunResult
from .companies import REGISTERED_COLLECTORS


class CareerCollectorRunner:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, settings.official_company_worker_count),
            thread_name_prefix="career-collector",
        )
        self._collectors = {
            collector.collector_key: collector for collector in REGISTERED_COLLECTORS
        }

    async def run(
        self,
        sources: list[CareerSiteSource],
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[CollectorRunResult]:
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                self._executor,
                self._run_single,
                source,
                search,
                profile,
            )
            for source in sources
        ]
        return await asyncio.gather(*tasks)

    def _run_single(
        self,
        source: CareerSiteSource,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> CollectorRunResult:
        collector = self._collectors.get(source.collector_key)
        if collector is None:
            return CollectorRunResult.not_implemented(source)
        return collector.timed_collect(source, search, profile, now_utc())


career_collector_runner = CareerCollectorRunner()
