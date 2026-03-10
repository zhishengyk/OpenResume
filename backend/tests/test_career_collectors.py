import asyncio
from datetime import datetime

from openresume_api.adapters.official import official_adapter
from openresume_api.career_collectors.base import (
    CareerSiteSource,
    CollectedJobRecord,
    CollectorRunResult,
    CompanyCollector,
)
from openresume_api.career_collectors.manifest import load_sources
from openresume_api.career_collectors.runner import CareerCollectorRunner
from openresume_api.models import CandidateProfile
from openresume_api.schemas import SearchSessionCreate


def make_search() -> SearchSessionCreate:
    return SearchSessionCreate(
        platforms=["official"],
        mode="recommend_only",
        job_targets=["前端工程师"],
        cities=["Shanghai"],
        salary_floor=0,
        must_have_keywords=[],
    )


def make_source(*, key: str, collector_key: str, variant: str) -> CareerSiteSource:
    return CareerSiteSource(
        key=key,
        company_name="ByteDance",
        entry_url="https://jobs.bytedance.com/",
        source_site="jobs.bytedance.com",
        collector_key=collector_key,
        variant=variant,
        label=key,
    )


def make_record(*, job_id: str, title: str = "Frontend Engineer") -> CollectedJobRecord:
    return CollectedJobRecord(
        source_company="ByteDance",
        source_site="jobs.bytedance.com",
        job_id=job_id,
        title=title,
        description_text="React TypeScript",
        requirements_text="React TypeScript",
        apply_url=f"https://jobs.bytedance.com/experienced/position/{job_id}/detail",
        lang="zh-CN",
        crawl_time=datetime(2026, 3, 10),
        raw_payload={"platform": "official"},
    )


def test_manifest_only_registers_bytedance_sources():
    sources = load_sources()
    assert [source.key for source in sources] == [
        "bytedance-experienced",
        "bytedance-campus",
    ]
    assert all(source.collector_key == "bytedance" for source in sources)


def test_runner_isolates_error_and_missing_collectors():
    class WorkingCollector(CompanyCollector):
        collector_key = "working"

        def collect(self, source, search, profile, now):
            return [make_record(job_id=f"{source.variant}-1")]

    class FailingCollector(CompanyCollector):
        collector_key = "failing"

        def collect(self, source, search, profile, now):
            raise RuntimeError("boom")

    runner = CareerCollectorRunner()
    runner._collectors = {
        "working": WorkingCollector(),
        "failing": FailingCollector(),
    }

    search = make_search()
    profile = CandidateProfile(id=1)
    results = asyncio.run(
        runner.run(
            [
                make_source(key="working", collector_key="working", variant="experienced"),
                make_source(key="failing", collector_key="failing", variant="campus"),
                make_source(key="missing", collector_key="missing", variant="campus"),
            ],
            search,
            profile,
        )
    )

    assert [result.status for result in results] == ["success", "error", "not_implemented"]
    assert results[0].jobs[0].job_id == "experienced-1"
    assert results[1].error == "boom"


def test_official_adapter_dedupes_records_by_source_site_and_job_id(monkeypatch):
    sources = list(load_sources())

    async def fake_run(sources_arg, search, profile):
        assert sources_arg == sources
        return [
            CollectorRunResult(
                source=sources[0],
                collector_key="bytedance",
                status="success",
                jobs=[
                    make_record(job_id="same-job"),
                    make_record(job_id="same-job"),
                    make_record(job_id="other-job"),
                ],
                stats={"returned_jobs": 3},
                duration_ms=10,
            ),
            CollectorRunResult.not_implemented(sources[1]),
        ]

    monkeypatch.setattr("openresume_api.adapters.official.load_sources", lambda: tuple(sources))
    monkeypatch.setattr("openresume_api.adapters.official.career_collector_runner.run", fake_run)

    drafts = asyncio.run(
        official_adapter.search_jobs(
            make_search(),
            CandidateProfile(id=1),
        )
    )

    assert sorted(draft.job_id for draft in drafts) == ["other-job", "same-job"]
    assert official_adapter.last_run_stats["sources_not_implemented"] == 1
    assert official_adapter.last_run_stats["jobs_before_dedupe"] == 3
    assert official_adapter.last_run_stats["jobs_after_dedupe"] == 2
