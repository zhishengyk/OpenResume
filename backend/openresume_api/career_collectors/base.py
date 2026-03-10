from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any

from ..models import CandidateProfile
from ..schemas import SearchSessionCreate


@dataclass(frozen=True)
class CareerSiteSource:
    key: str
    company_name: str
    entry_url: str
    source_site: str
    collector_key: str
    variant: str
    label: str


@dataclass
class CollectedJobRecord:
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
class CollectorRunResult:
    source: CareerSiteSource
    collector_key: str
    status: str
    jobs: list[CollectedJobRecord] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    @classmethod
    def not_implemented(cls, source: CareerSiteSource) -> "CollectorRunResult":
        return cls(
            source=source,
            collector_key=source.collector_key,
            status="not_implemented",
            jobs=[],
            stats={},
            duration_ms=0,
        )


class CompanyCollector:
    collector_key = "base"

    def matches(self, source: CareerSiteSource) -> bool:
        return source.collector_key == self.collector_key

    def collect(
        self,
        source: CareerSiteSource,
        search: SearchSessionCreate,
        profile: CandidateProfile,
        now: datetime,
    ) -> list[CollectedJobRecord]:
        raise NotImplementedError

    def timed_collect(
        self,
        source: CareerSiteSource,
        search: SearchSessionCreate,
        profile: CandidateProfile,
        now: datetime,
    ) -> CollectorRunResult:
        started_at = perf_counter()
        try:
            jobs = self.collect(source, search, profile, now)
            status = "success" if jobs else "empty"
            return CollectorRunResult(
                source=source,
                collector_key=self.collector_key,
                status=status,
                jobs=jobs,
                stats={"returned_jobs": len(jobs)},
                duration_ms=int((perf_counter() - started_at) * 1000),
            )
        except Exception as error:
            return CollectorRunResult(
                source=source,
                collector_key=self.collector_key,
                status="error",
                jobs=[],
                stats={},
                error=str(error) or error.__class__.__name__,
                duration_ms=int((perf_counter() - started_at) * 1000),
            )
