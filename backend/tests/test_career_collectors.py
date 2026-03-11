import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

from openresume_api.adapters.official import official_adapter
from openresume_api.career_collectors.base import (
    CareerSiteSource,
    CollectedJobRecord,
    CollectorRunResult,
    CompanyCollector,
)
from openresume_api.career_collectors.companies.alibaba_holding import (
    AlibabaHoldingCollector,
    alibaba_holding_collector,
)
from openresume_api.career_collectors.companies.bytedance import (
    BytedanceCollector,
    _first_nested_name,
    bytedance_collector,
)
from openresume_api.career_collectors.companies.meituan import (
    MeituanCollector,
    meituan_collector,
)
from openresume_api.career_collectors.companies.pdd import (
    PddCollector,
    pdd_collector,
)
from openresume_api.career_collectors.companies.tencent import (
    TencentCollector,
    tencent_collector,
)
from openresume_api.career_collectors.companies.taobao import (
    TaobaoCollector,
    taobao_collector,
)
from openresume_api.career_collectors.companies.aliyun import (
    AliyunCollector,
    aliyun_collector,
)
from openresume_api.career_collectors.manifest import filter_sources, load_sources
from openresume_api.career_collectors.normalization import (
    build_description_html,
    epoch_millis_to_datetime,
    normalize_city,
    normalize_multiline_text,
    normalize_whitespace,
)
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


def make_source(
    *,
    key: str,
    collector_key: str,
    variant: str,
    company_name: str = "ByteDance",
    entry_url: str = "https://jobs.bytedance.com/",
    source_site: str = "jobs.bytedance.com",
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


def test_manifest_registers_bytedance_and_tencent_sources():
    sources = load_sources()
    source_by_key = {source.key: source for source in sources}
    expected = {
        "bytedance-experienced": "bytedance",
        "bytedance-campus": "bytedance",
        "bytedance-internship": "bytedance",
        "tencent-experienced": "tencent",
        "tencent-campus": "tencent",
        "tencent-internship": "tencent",
        "taobao-experienced": "taobao",
        "taobao-campus": "taobao",
        "taobao-internship": "taobao",
        "aliyun-experienced": "aliyun",
        "aliyun-campus": "aliyun",
        "aliyun-internship": "aliyun",
        "alibaba-holding-experienced": "alibaba_holding",
        "alibaba-holding-campus": "alibaba_holding",
        "alibaba-holding-internship": "alibaba_holding",
        "meituan-experienced": "meituan",
        "pdd-campus": "pdd",
        "pdd-internship": "pdd",
    }
    assert expected.keys() <= source_by_key.keys()
    for key, collector_key in expected.items():
        assert source_by_key[key].collector_key == collector_key


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


class TestNormalizeWhitespace:
    def test_removes_extra_spaces(self):
        assert normalize_whitespace("  hello   world  ") == "hello world"

    def test_replaces_fullwidth_spaces(self):
        assert normalize_whitespace("hello\u3000world") == "hello world"

    def test_handles_empty_string(self):
        assert normalize_whitespace("") == ""

    def test_handles_none_like_input(self):
        assert normalize_whitespace(None) == ""


class TestNormalizeMultilineText:
    def test_removes_empty_lines(self):
        assert normalize_multiline_text("line1\n\nline2") == "line1\nline2"

    def test_strips_each_line(self):
        assert normalize_multiline_text("  line1  \n  line2  ") == "line1\nline2"

    def test_handles_empty_string(self):
        assert normalize_multiline_text("") == ""


class TestNormalizeCity:
    def test_normalizes_beijing_alias(self):
        assert normalize_city("beijing") == "北京"
        assert normalize_city("BEIJING") == "北京"

    def test_normalizes_shanghai_alias(self):
        assert normalize_city("shanghai") == "上海"

    def test_removes_city_suffix(self):
        assert normalize_city("杭州市") == "杭州"

    def test_handles_compound_location(self):
        assert normalize_city("北京·上海") == "北京"
        assert normalize_city("Shanghai, Beijing") == "Shanghai"

    def test_handles_empty_string(self):
        assert normalize_city("") == ""


class TestBuildDescriptionHtml:
    def test_creates_sections(self):
        html = build_description_html("做事情", "有经验")
        assert "<h2>职位描述</h2>" in html
        assert "<h2>任职要求</h2>" in html
        assert "<p>做事情</p>" in html
        assert "<p>有经验</p>" in html

    def test_escapes_html_content(self):
        html = build_description_html("<script>alert('xss')</script>", "")
        assert "&lt;script&gt;" in html
        assert "<script>" not in html

    def test_handles_empty_requirements(self):
        html = build_description_html("description", "")
        assert "<h2>职位描述</h2>" in html
        assert "<h2>任职要求</h2>" not in html


class TestEpochMillisToDatetime:
    def test_converts_millis_to_datetime(self):
        result = epoch_millis_to_datetime(1704067200000)
        assert result is not None
        assert result.year == 2024

    def test_handles_none(self):
        assert epoch_millis_to_datetime(None) is None

    def test_handles_empty_string(self):
        assert epoch_millis_to_datetime("") is None

    def test_handles_invalid_value(self):
        assert epoch_millis_to_datetime("invalid") is None


class TestFirstNestedName:
    def test_extracts_name_key(self):
        assert _first_nested_name({"name": "Engineering"}) == "Engineering"

    def test_extracts_i18n_name_key(self):
        assert _first_nested_name({"i18n_name": "工程部门"}) == "工程部门"

    def test_extracts_en_name_key(self):
        assert _first_nested_name({"en_name": "Engineering Dept"}) == "Engineering Dept"

    def test_prioritizes_name_over_others(self):
        assert _first_nested_name({"name": "Primary", "i18n_name": "Secondary"}) == "Primary"

    def test_returns_empty_for_non_dict(self):
        assert _first_nested_name("not a dict") == ""
        assert _first_nested_name(None) == ""
        assert _first_nested_name([]) == ""

    def test_returns_empty_for_empty_or_whitespace(self):
        assert _first_nested_name({"name": "  "}) == ""
        assert _first_nested_name({"name": ""}) == ""


class TestBytedanceCollector:
    def test_collector_key_is_bytedance(self):
        assert bytedance_collector.collector_key == "bytedance"

    def test_to_record_returns_none_for_missing_job_id(self):
        collector = BytedanceCollector()
        source = make_source(key="test", collector_key="bytedance", variant="experienced")
        provider = MagicMock()
        provider.detail_url.return_value = "https://example.com/job/123"

        result = collector._to_record(
            source,
            {"id": "", "title": "Engineer"},
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is None

    def test_to_record_returns_none_for_missing_title(self):
        collector = BytedanceCollector()
        source = make_source(key="test", collector_key="bytedance", variant="experienced")
        provider = MagicMock()
        provider.detail_url.return_value = "https://example.com/job/123"

        result = collector._to_record(
            source,
            {"id": "123", "title": ""},
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is None

    def test_to_record_extracts_basic_fields(self):
        collector = BytedanceCollector()
        source = make_source(key="test", collector_key="bytedance", variant="experienced")
        provider = MagicMock()
        provider.detail_url.return_value = "https://jobs.bytedance.com/experienced/position/123/detail"

        result = collector._to_record(
            source,
            {
                "id": "123",
                "title": "Senior Frontend Engineer",
                "description": "Build amazing products",
                "requirement": "React TypeScript",
                "city_info": {"name": "上海"},
                "job_category": {"name": "Engineering"},
                "publish_time": 1704067200000,
            },
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )

        assert result is not None
        assert result.job_id == "123"
        assert result.title == "Senior Frontend Engineer"
        assert result.description_text == "Build amazing products"
        assert result.requirements_text == "React TypeScript"
        assert result.location_city == "上海"
        assert result.department == "Engineering"
        assert result.employment_type == "社招"
        assert result.source_company == "字节跳动"

    def test_to_record_uses_campus_variant(self):
        collector = BytedanceCollector()
        source = make_source(key="test", collector_key="bytedance", variant="campus")
        provider = MagicMock()
        provider.detail_url.return_value = "https://jobs.bytedance.com/campus/position/123/detail"

        result = collector._to_record(
            source,
            {"id": "123", "title": "Engineer"},
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )

        assert result is not None
        assert result.employment_type == "校招"

    def test_to_record_falls_back_to_location_field(self):
        collector = BytedanceCollector()
        source = make_source(key="test", collector_key="bytedance", variant="experienced")
        provider = MagicMock()
        provider.detail_url.return_value = "https://example.com/job/123"

        result = collector._to_record(
            source,
            {"id": "123", "title": "Engineer", "location": "Beijing"},
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )

        assert result is not None
        assert result.location_raw == "Beijing"

    def test_to_record_falls_back_to_job_function_for_department(self):
        collector = BytedanceCollector()
        source = make_source(key="test", collector_key="bytedance", variant="experienced")
        provider = MagicMock()
        provider.detail_url.return_value = "https://example.com/job/123"

        result = collector._to_record(
            source,
            {"id": "123", "title": "Engineer", "job_function": {"name": "Frontend"}},
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )

        assert result is not None
        assert result.department == "Frontend"


class TestFilterSources:
    def test_filters_by_variant(self):
        sources = load_sources()
        filtered = filter_sources(sources, variants=["experienced"])
        assert len(filtered) >= 5
        assert all(source.variant == "experienced" for source in filtered)
        collector_keys = {source.collector_key for source in filtered}
        assert {
            "bytedance",
            "tencent",
            "taobao",
            "aliyun",
            "alibaba_holding",
        } <= collector_keys

    def test_filters_by_company(self):
        sources = load_sources()
        filtered = filter_sources(sources, companies=["字节跳动"])
        assert len(filtered) == 3
        assert all(source.collector_key == "bytedance" for source in filtered)

    def test_filters_by_tencent_company(self):
        sources = load_sources()
        filtered = filter_sources(sources, companies=["腾讯"])
        assert len(filtered) == 3
        assert all(source.collector_key == "tencent" for source in filtered)

    def test_filters_by_both(self):
        sources = load_sources()
        filtered = filter_sources(sources, variants=["campus"], companies=["字节跳动"])
        assert len(filtered) == 1
        assert filtered[0].variant == "campus"

    def test_filters_tencent_internship(self):
        sources = load_sources()
        filtered = filter_sources(sources, variants=["internship"], companies=["腾讯"])
        assert len(filtered) == 1
        assert filtered[0].collector_key == "tencent"
        assert filtered[0].variant == "internship"

    def test_filters_by_taobao_company(self):
        sources = load_sources()
        filtered = filter_sources(sources, companies=["淘天集团"])
        assert len(filtered) == 3
        assert all(source.collector_key == "taobao" for source in filtered)

    def test_filters_by_aliyun_company(self):
        sources = load_sources()
        filtered = filter_sources(sources, companies=["阿里云"])
        assert len(filtered) == 3
        assert all(source.collector_key == "aliyun" for source in filtered)

    def test_filters_by_alibaba_holding_company(self):
        sources = load_sources()
        filtered = filter_sources(sources, companies=["阿里控股"])
        assert len(filtered) == 3
        assert all(source.collector_key == "alibaba_holding" for source in filtered)

    def test_filters_by_meituan_company(self):
        sources = load_sources()
        filtered = filter_sources(sources, companies=["美团"])
        assert len(filtered) == 1
        assert filtered[0].collector_key == "meituan"

    def test_filters_by_pdd_company(self):
        sources = load_sources()
        filtered = filter_sources(sources, companies=["拼多多"])
        assert len(filtered) == 2
        assert all(source.collector_key == "pdd" for source in filtered)

    def test_returns_all_when_no_filters(self):
        sources = load_sources()
        filtered = filter_sources(sources)
        assert len(filtered) == len(sources)

    def test_returns_empty_when_no_match(self):
        sources = load_sources()
        filtered = filter_sources(sources, variants=["nonexistent"])
        assert len(filtered) == 0


class TestCollectorRunResult:
    def test_not_implemented_result(self):
        source = make_source(key="test", collector_key="test", variant="experienced")
        result = CollectorRunResult.not_implemented(source)
        assert result.status == "not_implemented"
        assert result.jobs == []
        assert result.collector_key == "test"

    def test_success_result_with_stats(self):
        source = make_source(key="test", collector_key="test", variant="experienced")
        result = CollectorRunResult(
            source=source,
            collector_key="test",
            status="success",
            jobs=[make_record(job_id="1")],
            stats={"returned_jobs": 1},
            duration_ms=100,
        )
        assert result.status == "success"
        assert len(result.jobs) == 1
        assert result.duration_ms == 100


class TestTencentCollector:
    def test_collector_key_is_tencent(self):
        assert tencent_collector.collector_key == "tencent"

    def test_to_record_returns_none_for_missing_job_id(self):
        collector = TencentCollector()
        source = make_source(
            key="test",
            collector_key="tencent",
            variant="experienced",
            company_name="Tencent",
            entry_url="https://careers.tencent.com/",
            source_site="careers.tencent.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = "https://careers.tencent.com/jobdesc.html?postId=1"
        result = collector._to_record(
            source,
            {"PostId": "", "RecruitPostName": "Engineer"},
            careers_provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is None

    def test_to_record_maps_fields(self):
        collector = TencentCollector()
        source = make_source(
            key="test",
            collector_key="tencent",
            variant="experienced",
            company_name="Tencent",
            entry_url="https://careers.tencent.com/",
            source_site="careers.tencent.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = "https://careers.tencent.com/jobdesc.html?postId=123"
        result = collector._to_record(
            source,
            {
                "PostId": "123",
                "RecruitPostName": "Frontend Engineer",
                "LocationName": "Shanghai",
                "CategoryName": "技术",
                "CountryName": "中国",
                "Responsibility": "Build product",
                "LastUpdateTime": "2026年03月10日",
                "PostURL": "http://careers.tencent.com/jobdesc.html?postId=123",
            },
            careers_provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.job_id == "123"
        assert result.title == "Frontend Engineer"
        assert result.location_raw == "Shanghai"
        assert result.location_city == "上海"
        assert result.department == "技术"
        assert result.description_text == "Build product"
        assert result.employment_type == "社招"
        assert result.source_company == "腾讯"
        assert result.source_site == "careers.tencent.com"
        assert result.posted_at is not None

    def test_to_record_campus_type(self):
        collector = TencentCollector()
        source = make_source(
            key="test",
            collector_key="tencent",
            variant="campus",
            company_name="Tencent",
            entry_url="https://careers.tencent.com/",
            source_site="careers.tencent.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = "https://careers.tencent.com/jobdesc.html?postId=123"
        result = collector._to_record(
            source,
            {"PostId": "123", "RecruitPostName": "Engineer"},
            careers_provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.employment_type == "校招"



    def test_to_record_maps_joinqq_fields(self):
        collector = TencentCollector()
        source = make_source(
            key="test",
            collector_key="tencent",
            variant="internship",
            company_name="Tencent",
            entry_url="https://join.qq.com/post.html?query=p_2",
            source_site="careers.tencent.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = "https://careers.tencent.com/jobdesc.html?postId=123"
        result = collector._to_record(
            source,
            {
                "postId": "1200791473415778304",
                "positionTitle": "Frontend Engineer",
                "workCities": "Shenzhen Beijing",
                "projectName": "Internship",
                "recruitLabelName": "Internship",
                "__source_site": "join.qq.com",
            },
            careers_provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.job_id == "1200791473415778304"
        assert result.title == "Frontend Engineer"
        assert result.employment_type == "\u5b9e\u4e60"
        assert result.source_site == "join.qq.com"
        assert "join.qq.com/post_detail.html" in result.apply_url


class TestTaobaoCollector:
    def test_collector_key_is_taobao(self):
        assert taobao_collector.collector_key == "taobao"

    def test_to_record_returns_none_for_missing_job_id(self):
        collector = TaobaoCollector()
        source = make_source(
            key="test",
            collector_key="taobao",
            variant="experienced",
            company_name="淘天集团",
            entry_url="https://talent.taotian.com/",
            source_site="talent.taotian.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = (
            "https://talent.taotian.com/off-campus/position-detail?positionId=1"
        )
        result = collector._to_record(
            source,
            {"id": "", "name": "Engineer"},
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is None

    def test_to_record_maps_fields(self):
        collector = TaobaoCollector()
        source = make_source(
            key="test",
            collector_key="taobao",
            variant="internship",
            company_name="淘天集团",
            entry_url=(
                "https://talent.taotian.com/campus/position-list"
                "?campusType=internship&lang=zh"
            ),
            source_site="talent.taotian.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = (
            "https://talent.taotian.com/campus/position-detail"
            "?positionId=123&campusType=internship"
        )
        result = collector._to_record(
            source,
            {
                "id": "123",
                "name": "Frontend Engineer",
                "description": "Build products",
                "requirement": "React TypeScript",
                "workLocations": ["Hangzhou", "Beijing"],
                "categoryName": "Engineering",
                "publishTime": 1704067200000,
                "positionUrl": "/campus/position-detail?positionId=123&campusType=internship",
            },
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.job_id == "123"
        assert result.title == "Frontend Engineer"
        assert result.location_raw == "Hangzhou / Beijing"
        assert result.location_city == "杭州"
        assert result.department == "Engineering"
        assert result.description_text == "Build products"
        assert result.requirements_text == "React TypeScript"
        assert result.employment_type == "实习"
        assert result.source_company == "淘天集团"
        assert result.source_site == "talent.taotian.com"
        assert result.posted_at is not None

class TestAliyunCollector:
    def test_collector_key_is_aliyun(self):
        assert aliyun_collector.collector_key == "aliyun"

    def test_to_record_returns_none_for_missing_job_id(self):
        collector = AliyunCollector()
        source = make_source(
            key="test",
            collector_key="aliyun",
            variant="experienced",
            company_name="阿里云",
            entry_url="https://careers.aliyun.com/off-campus/position-list?lang=zh",
            source_site="careers.aliyun.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = (
            "https://careers.aliyun.com/off-campus/position-detail?positionId=1"
        )
        result = collector._to_record(
            source,
            {"id": "", "name": "Engineer"},
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is None

    def test_to_record_maps_fields(self):
        collector = AliyunCollector()
        source = make_source(
            key="test",
            collector_key="aliyun",
            variant="campus",
            company_name="阿里云",
            entry_url=(
                "https://careers.aliyun.com/campus/position-list"
                "?campusType=freshman&lang=zh"
            ),
            source_site="careers.aliyun.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = (
            "https://careers.aliyun.com/campus/position-detail"
            "?positionId=123&campusType=freshman"
        )
        result = collector._to_record(
            source,
            {
                "id": "123",
                "name": "Frontend Engineer",
                "description": "Build products",
                "requirement": "React TypeScript",
                "workLocations": ["Hangzhou", "Beijing"],
                "categoryName": "Engineering",
                "publishTime": 1704067200000,
                "positionUrl": "/campus/position-detail?positionId=123&campusType=freshman",
            },
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.job_id == "123"
        assert result.title == "Frontend Engineer"
        assert result.location_raw == "Hangzhou / Beijing"
        assert result.location_city == "杭州"
        assert result.department == "Engineering"
        assert result.description_text == "Build products"
        assert result.requirements_text == "React TypeScript"
        assert result.employment_type == "校招"
        assert result.source_company == "阿里云"
        assert result.source_site == "careers.aliyun.com"
        assert result.posted_at is not None


class TestAlibabaHoldingCollector:
    def test_collector_key_is_alibaba_holding(self):
        assert alibaba_holding_collector.collector_key == "alibaba_holding"

    def test_to_record_maps_fields(self):
        collector = AlibabaHoldingCollector()
        source = make_source(
            key="test",
            collector_key="alibaba_holding",
            variant="experienced",
            company_name="阿里控股",
            entry_url="https://talent-holding.alibaba.com/",
            source_site="talent-holding.alibaba.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = (
            "https://talent-holding.alibaba.com/off-campus/position-detail?positionId=123"
        )
        result = collector._to_record(
            source,
            {
                "id": "123",
                "name": "Frontend Engineer",
                "description": "Build platforms",
                "requirement": "React TypeScript",
                "workLocations": ["Hangzhou"],
                "categoryName": "Engineering",
                "publishTime": 1704067200000,
            },
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.source_company == "阿里控股"
        assert result.source_site == "talent-holding.alibaba.com"
        assert result.employment_type == "社招"


class TestMeituanCollector:
    def test_collector_key_is_meituan(self):
        assert meituan_collector.collector_key == "meituan"

    def test_to_record_maps_fields(self):
        collector = MeituanCollector()
        source = make_source(
            key="test",
            collector_key="meituan",
            variant="experienced",
            company_name="美团",
            entry_url="https://zhaopin.meituan.com/web/social",
            source_site="zhaopin.meituan.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = (
            "https://zhaopin.meituan.com/web/position/detail?jobUnionId=123"
        )
        result = collector._to_record(
            source,
            {
                "jobUnionId": "123",
                "name": "Frontend Engineer",
                "cityList": [{"name": "北京"}],
                "department": [{"name": "平台研发"}],
                "jobDuty": "Build products",
                "jobRequirement": "React TypeScript",
                "firstPostTime": 1704067200000,
            },
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.source_company == "美团"
        assert result.source_site == "zhaopin.meituan.com"
        assert result.employment_type == "社招"
        assert result.location_city == "北京"


class TestPddCollector:
    def test_collector_key_is_pdd(self):
        assert pdd_collector.collector_key == "pdd"

    def test_to_record_maps_fields(self):
        collector = PddCollector()
        source = make_source(
            key="test",
            collector_key="pdd",
            variant="internship",
            company_name="拼多多",
            entry_url="https://careers.pddglobalhr.com/campus/intern",
            source_site="careers.pddglobalhr.com",
        )
        provider = MagicMock()
        provider.detail_url.return_value = (
            "https://careers.pddglobalhr.com/campus/intern/detail?positionId=123"
        )
        result = collector._to_record(
            source,
            {
                "id": "123",
                "name": "Web Frontend Intern",
                "workLocationName": "上海",
                "jobName": "技术",
                "jobDuty": "Build products",
                "serveRequirement": "React TypeScript",
                "releaseTime": 1704067200000,
            },
            provider=provider,
            crawl_time=datetime(2026, 3, 10),
        )
        assert result is not None
        assert result.source_company == "拼多多"
        assert result.source_site == "careers.pddglobalhr.com"
        assert result.employment_type == "实习"
        assert result.location_city == "上海"
