from datetime import datetime
from unittest.mock import MagicMock

import pytest

from openresume_api.career_collectors.base import CareerSiteSource
from openresume_api.career_collectors.companies.bilibili import BilibiliCollector
from openresume_api.career_collectors.companies.dewu import DewuCollector
from openresume_api.career_collectors.companies.freshippo import FreshippoCollector
from openresume_api.career_collectors.companies.mihoyo import MihoyoCollector
from openresume_api.career_collectors.companies.xiaohongshu import XiaohongshuCollector
from openresume_api.career_collectors.manifest import filter_sources, load_sources
from openresume_api.career_collectors.providers.freshippo_careers import (
    VARIANT_CONFIGS as FRESHIPPO_VARIANT_CONFIGS,
    FreshippoCareerClient,
)
from openresume_api.models import CandidateProfile
from openresume_api.schemas import SearchSessionCreate


def make_source(
    *,
    key: str,
    collector_key: str,
    variant: str,
    company_name: str,
    entry_url: str,
    source_site: str,
) -> CareerSiteSource:
    return CareerSiteSource(
        key=key,
        company_name=company_name,
        entry_url=entry_url,
        source_site=source_site,
        collector_key=collector_key,
        variant=variant,
        label=key,
    )


def make_search() -> SearchSessionCreate:
    return SearchSessionCreate(
        platforms=["official"],
        mode="recommend_only",
        job_targets=["Frontend Engineer"],
        cities=["Shanghai"],
        salary_floor=0,
        must_have_keywords=[],
        source_variants=["experienced"],
        source_companies=[],
        company_job_limit=6,
    )


def test_manifest_registers_new_company_sources():
    sources = load_sources()
    source_by_key = {source.key: source for source in sources}
    expected = {
        "xiaohongshu-experienced": "xiaohongshu",
        "xiaohongshu-campus": "xiaohongshu",
        "xiaohongshu-internship": "xiaohongshu",
        "bilibili-experienced": "bilibili",
        "bilibili-campus": "bilibili",
        "bilibili-internship": "bilibili",
        "dewu-experienced": "dewu",
        "dewu-campus": "dewu",
        "dewu-internship": "dewu",
        "freshippo-experienced": "freshippo",
        "freshippo-campus": "freshippo",
        "freshippo-internship": "freshippo",
        "mihoyo-experienced": "mihoyo",
        "mihoyo-campus": "mihoyo",
        "mihoyo-internship": "mihoyo",
    }

    assert expected.keys() <= source_by_key.keys()
    for key, collector_key in expected.items():
        assert source_by_key[key].collector_key == collector_key


@pytest.mark.parametrize(
    ("company_name", "collector_key"),
    [
        ("\u5c0f\u7ea2\u4e66", "xiaohongshu"),
        ("\u54d4\u54e9\u54d4\u54e9", "bilibili"),
        ("\u5f97\u7269", "dewu"),
        ("\u76d2\u9a6c", "freshippo"),
        ("\u7c73\u54c8\u6e38", "mihoyo"),
    ],
)
def test_filter_sources_supports_new_companies(company_name: str, collector_key: str):
    filtered = filter_sources(load_sources(), companies=[company_name])

    assert len(filtered) == 3
    assert all(source.collector_key == collector_key for source in filtered)


def test_xiaohongshu_collector_maps_fields():
    collector = XiaohongshuCollector()
    source = make_source(
        key="xiaohongshu-campus",
        collector_key="xiaohongshu",
        variant="campus",
        company_name="\u5c0f\u7ea2\u4e66",
        entry_url="https://job.xiaohongshu.com/campus",
        source_site="job.xiaohongshu.com",
    )
    provider = MagicMock()
    provider.detail_url.return_value = "https://job.xiaohongshu.com/campus/position/123"

    result = collector._to_record(
        source,
        {
            "positionId": "123",
            "positionName": "Frontend Engineer",
            "duty": "Build products",
            "qualification": "React TypeScript",
            "workplace": "\u4e0a\u6d77",
            "jobType": "Engineering",
            "publishTime": "2026-03-10",
        },
        provider=provider,
        crawl_time=datetime(2026, 3, 10),
    )

    assert result is not None
    assert result.source_company == "\u5c0f\u7ea2\u4e66"
    assert result.title == "Frontend Engineer"
    assert result.location_city == "\u4e0a\u6d77"
    assert result.department == "Engineering"
    assert result.employment_type == "\u6821\u62db"
    assert result.posted_at is not None


def test_bilibili_collector_maps_fields():
    collector = BilibiliCollector()
    source = make_source(
        key="bilibili-experienced",
        collector_key="bilibili",
        variant="experienced",
        company_name="\u54d4\u54e9\u54d4\u54e9",
        entry_url="https://jobs.bilibili.com/",
        source_site="jobs.bilibili.com",
    )
    provider = MagicMock()
    provider.detail_url.return_value = "https://jobs.bilibili.com/social/positions/99"

    result = collector._to_record(
        source,
        {
            "id": "99",
            "positionName": "Frontend Engineer",
            "positionDescription": "Build products",
            "workLocation": "\u4e0a\u6d77",
            "postCodeName": "Engineering",
            "pushTime": "2026-03-10 09:00:00",
            "positionTypeName": "\u6b63\u5f0f",
        },
        provider=provider,
        crawl_time=datetime(2026, 3, 10),
    )

    assert result is not None
    assert result.source_company == "\u54d4\u54e9\u54d4\u54e9"
    assert result.description_text == "Build products"
    assert result.location_city == "\u4e0a\u6d77"
    assert result.employment_type == "\u793e\u62db"
    assert result.posted_at is not None


def test_dewu_collector_maps_fields():
    collector = DewuCollector()
    source = make_source(
        key="dewu-experienced",
        collector_key="dewu",
        variant="experienced",
        company_name="\u5f97\u7269",
        entry_url="https://poizon.jobs.feishu.cn/index",
        source_site="poizon.jobs.feishu.cn",
    )
    provider = MagicMock()
    provider.detail_url.return_value = "https://poizon.jobs.feishu.cn/index/position/7/detail"

    result = collector._to_record(
        source,
        {
            "id": "7",
            "title": "Platform Engineer",
            "description": "Build systems",
            "requirement": "Distributed systems",
            "city_info": {"name": "\u5317\u4eac"},
            "job_category": {"name": "Engineering"},
            "publish_time": 1704067200000,
        },
        provider=provider,
        crawl_time=datetime(2026, 3, 10),
    )

    assert result is not None
    assert result.source_company == "\u5f97\u7269"
    assert result.location_city == "\u5317\u4eac"
    assert result.department == "Engineering"
    assert result.employment_type == "\u793e\u62db"
    assert result.posted_at is not None


def test_freshippo_collector_maps_fields():
    collector = FreshippoCollector()
    source = make_source(
        key="freshippo-internship",
        collector_key="freshippo",
        variant="internship",
        company_name="\u76d2\u9a6c",
        entry_url="https://hire.freshippo.com/campus/home?lang=zh",
        source_site="hire.freshippo.com",
    )
    provider = MagicMock()
    provider.detail_url.return_value = (
        "https://hire.freshippo.com/campus/position-detail?positionId=15"
    )

    result = collector._to_record(
        source,
        {
            "id": "15",
            "name": "Retail Tech Intern",
            "description": "Build retail tooling",
            "requirement": "Python SQL",
            "workLocations": ["\u676d\u5dde", "\u4e0a\u6d77"],
            "categoryName": "Engineering",
            "publishTime": 1704067200000,
            "positionUrl": "/campus/position-detail?positionId=15",
        },
        provider=provider,
        crawl_time=datetime(2026, 3, 10),
    )

    assert result is not None
    assert result.source_company == "\u76d2\u9a6c"
    assert result.location_raw == "\u676d\u5dde / \u4e0a\u6d77"
    assert result.location_city == "\u676d\u5dde"
    assert result.employment_type == "\u5b9e\u4e60"
    assert result.posted_at is not None


def test_freshippo_variant_configs_reuse_alibaba_shell():
    assert FRESHIPPO_VARIANT_CONFIGS["experienced"].channel == "hema_group_official_site"
    assert FRESHIPPO_VARIANT_CONFIGS["campus"].channel == "hema_campus_group_official_site"
    assert FRESHIPPO_VARIANT_CONFIGS["internship"].category_type == "internship"

    client = FreshippoCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert (
        client.detail_url(variant="campus", job_id="88")
        == "https://hire.freshippo.com/campus/position-detail?positionId=88"
    )


def test_mihoyo_collector_collect_fetches_detail_before_mapping(monkeypatch):
    observed: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            observed["init"] = kwargs

        def collect_jobs(self, *, variant: str, keywords: list[str], limit: int | None):
            observed["collect"] = {
                "variant": variant,
                "keywords": keywords,
                "limit": limit,
            }
            return [{"id": "7242", "title": "Rendering Engineer"}]

        def fetch_detail(self, *, variant: str, job_id: str):
            observed["detail"] = {"variant": variant, "job_id": job_id}
            return {
                "id": "7242",
                "title": "Rendering Engineer",
                "description": "Build engine tooling",
                "jobRequire": "C++",
                "addition": "Rendering pipeline",
                "competencyType": "Engine",
                "addressDetailList": [{"addressDetail": "\u4e0a\u6d77"}],
            }

        def detail_url(self, *, variant: str, job_id: str):
            return f"https://jobs.mihoyo.com/m/#/position/{job_id}"

    monkeypatch.setattr(
        "openresume_api.career_collectors.companies.mihoyo.MihoyoJobsClient",
        FakeProvider,
    )

    collector = MihoyoCollector()
    source = make_source(
        key="mihoyo-experienced",
        collector_key="mihoyo",
        variant="experienced",
        company_name="\u7c73\u54c8\u6e38",
        entry_url="https://jobs.mihoyo.com/m/#/position",
        source_site="jobs.mihoyo.com",
    )
    records = collector.collect(
        source,
        make_search(),
        CandidateProfile(id=1),
        datetime(2026, 3, 10),
    )

    assert len(records) == 1
    assert observed["collect"] == {
        "variant": "experienced",
        "keywords": ["Frontend Engineer"],
        "limit": 6,
    }
    assert observed["detail"] == {"variant": "experienced", "job_id": "7242"}
    assert records[0].source_company == "\u7c73\u54c8\u6e38"
    assert records[0].location_city == "\u4e0a\u6d77"
    assert records[0].employment_type == "\u793e\u62db"
