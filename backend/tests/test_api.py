import asyncio
import time
from datetime import datetime, timedelta

import openresume_api.services.profile as profile_module
from openresume_api import db as db_module
from openresume_api.adapters.base import NormalizedJobDraft, PlatformBlockedError
from openresume_api.adapters.official import official_adapter
from openresume_api.career_collectors import career_collector_runner
from openresume_api.models import AppSetting, CandidateProfile, JobListing, SearchFetchCache
from openresume_api.schemas import SearchSessionCreate
from openresume_api.services.llm import (
    AnalysisBatch,
    AnalysisMetadata,
    LLMResult,
    OpenAICompatibleLLMProvider,
    llm_service,
)
from openresume_api.services.profile import profile_service
from openresume_api.services.runtime_config import runtime_config_service
from openresume_api.services.search import search_service
from sqlmodel import Session, select


def wait_for_session_status(client, session_id: str, expected: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = client.get(f"/api/search-sessions/{session_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] == expected:
            return latest
        time.sleep(0.15)
    raise AssertionError(f"session {session_id} did not reach status={expected}: {latest}")


def wait_for_analysis_status(client, session_id: str, expected: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = client.get(f"/api/search-sessions/{session_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["analysis_status"] == expected:
            return latest
        time.sleep(0.15)
    raise AssertionError(
        f"session {session_id} did not reach analysis_status={expected}: {latest}"
    )


def upsert_profile(client, *, with_resume: bool = False):
    response = client.put(
        "/api/profile",
        json={
            "id": 1,
            "full_name": "Test Candidate",
            "headline": "Senior Frontend Engineer",
            "summary": "React and TypeScript engineer",
            "target_roles": ["Frontend Engineer", "Full Stack Engineer"],
            "preferred_cities": ["Shanghai", "Hangzhou"],
            "salary_floor": 25000,
            "years_experience": 5,
            "degree": "Bachelor",
            "skills": ["React", "TypeScript", "Node.js", "FastAPI"],
            "must_have_keywords": ["React", "TypeScript"],
            "tech_stack": ["React", "TypeScript", "Node.js"],
            "project_experiences": [
                {
                    "name": "OpenResume Search",
                    "role": "Lead Engineer",
                    "summary": "Built ranking pipeline and responsive search UI",
                    "technologies": ["React", "TypeScript", "FastAPI"],
                }
            ],
            "awards": [
                {
                    "title": "Hackathon Winner",
                    "issuer": "OpenResume Lab",
                    "year": "2024",
                    "summary": "Won first place for search quality improvements",
                }
            ],
            "source_filename": "resume.pdf" if with_resume else None,
            "source_language": "zh-CN",
            "raw_text": "React TypeScript resume",
        },
    )
    assert response.status_code == 200


def create_search_session(
    client,
    *,
    platforms: list[str] | None = None,
    mode: str = "recommend_only",
    source_variants: list[str] | None = None,
    source_companies: list[str] | None = None,
    job_targets: list[str] | None = None,
    cities: list[str] | None = None,
    salary_floor: int = 25000,
    must_have_keywords: list[str] | None = None,
    match_limit: int = 200,
    company_job_limit: int = 200,
    force_refresh: bool = False,
):
    return client.post(
        "/api/search-sessions",
        json={
            "platforms": ["official"] if platforms is None else platforms,
            "mode": mode,
            "job_targets": (
                ["Frontend Engineer", "Full Stack Engineer"]
                if job_targets is None
                else job_targets
            ),
            "cities": ["Shanghai", "Hangzhou"] if cities is None else cities,
            "salary_floor": salary_floor,
            "must_have_keywords": (
                ["React", "TypeScript"]
                if must_have_keywords is None
                else must_have_keywords
            ),
            "source_variants": [] if source_variants is None else source_variants,
            "source_companies": [] if source_companies is None else source_companies,
            "match_limit": match_limit,
            "company_job_limit": company_job_limit,
            "force_refresh": force_refresh,
        },
    )


def sample_draft() -> NormalizedJobDraft:
    return NormalizedJobDraft(
        source_company="ByteDance",
        source_site="jobs.bytedance.com",
        job_id="official-live-001",
        title="Senior Frontend Engineer",
        department="Engineering",
        employment_type="Experienced",
        location_raw="Shanghai",
        location_city="Shanghai",
        location_country="China",
        remote_type="onsite",
        description_html="<p>React TypeScript Electron FastAPI official site flow</p>",
        description_text="React TypeScript Electron FastAPI official site flow",
        requirements_text="React TypeScript",
        skills_extracted=[],
        posted_at=datetime(2026, 3, 1),
        apply_url="https://jobs.bytedance.com/experienced/position/official-live-001/detail",
        salary_raw="25K-35K",
        salary_min=25000,
        salary_max=35000,
        lang="zh-CN",
        crawl_time=datetime(2026, 3, 10),
        raw_payload={"source": "test", "platform": "official"},
    )


def sample_drafts(count: int) -> list[NormalizedJobDraft]:
    drafts: list[NormalizedJobDraft] = []
    for index in range(count):
        draft = sample_draft()
        draft.job_id = f"official-live-{index:03d}"
        draft.title = f"Frontend Engineer {index}"
        draft.apply_url = (
            f"https://jobs.bytedance.com/experienced/position/{draft.job_id}/detail"
        )
        drafts.append(draft)
    return drafts


def variant_draft(
    *,
    job_id: str,
    location_city: str,
    apply_suffix: str,
    title: str = "Senior Frontend Engineer",
    description_text: str | None = None,
    requirements_text: str | None = None,
    employment_type: str | None = None,
) -> NormalizedJobDraft:
    draft = sample_draft()
    draft.job_id = job_id
    draft.title = title
    draft.location_city = location_city
    draft.location_raw = location_city
    if description_text is not None:
        draft.description_text = description_text
    if requirements_text is not None:
        draft.requirements_text = requirements_text
    if employment_type is not None:
        draft.employment_type = employment_type
    draft.apply_url = (
        f"https://jobs.bytedance.com/experienced/position/{job_id}/{apply_suffix}"
    )
    return draft


def company_draft(
    *,
    job_id: str,
    source_company: str,
    title: str = "Senior Frontend Engineer",
    description_text: str | None = None,
    requirements_text: str | None = None,
) -> NormalizedJobDraft:
    draft = sample_draft()
    draft.job_id = job_id
    draft.source_company = source_company
    normalized_company = source_company.replace(" ", "").lower() or "company"
    draft.source_site = f"{normalized_company}.example.com"
    draft.title = title
    if description_text is not None:
        draft.description_text = description_text
    if requirements_text is not None:
        draft.requirements_text = requirements_text
    draft.apply_url = f"https://{draft.source_site}/jobs/{job_id}"
    return draft


def test_disclaimer_flow(client):
    first = client.get("/api/app-state")
    assert first.status_code == 200
    assert first.json()["launch_disclaimer_required"] is True

    consent = client.post(
        "/api/risk-consents",
        json={"consent_type": "launch_disclaimer", "version": "1.0.0"},
    )
    assert consent.status_code == 200

    second = client.get("/api/app-state")
    assert second.json()["launch_disclaimer_required"] is False


def test_platform_registry_returns_official_and_disabled_boss(client):
    response = client.get("/api/platforms")
    assert response.status_code == 200
    payload = response.json()

    assert [item["platform"] for item in payload] == ["official", "boss"]
    assert payload[0]["selectable"] is True
    assert payload[1]["selectable"] is False
    assert "未启用" in payload[1]["disabled_reason"]


def test_runtime_config_exposes_llm_status_without_secrets(client):
    response = client.get("/api/runtime-config")
    assert response.status_code == 200

    payload = response.json()
    assert payload["api_port"] == 38417
    assert payload["llm_provider"] == "heuristic"
    assert payload["llm_effective_provider"] == "heuristic"
    assert payload["llm_configured"] is False
    assert payload["llm_notice"]
    assert "OPENRESUME_OPENAI_API_KEY" in payload["llm_missing_envs"]
    assert "字节跳动" in payload["official_sources_summary"]
    assert "腾讯" in payload["official_sources_summary"]
    assert "\u6dd8\u5929\u96c6\u56e2" in payload["official_sources_summary"]
    assert "\u963f\u91cc\u4e91" in payload["official_sources_summary"]
    assert "\u963f\u91cc\u63a7\u80a1" in payload["official_sources_summary"]
    assert "\u7f8e\u56e2" in payload["official_sources_summary"]
    assert "\u62fc\u591a\u591a" in payload["official_sources_summary"]
    assert "\u5c0f\u7ea2\u4e66" in payload["official_sources_summary"]
    assert "\u54d4\u54e9\u54d4\u54e9" in payload["official_sources_summary"]
    assert "\u5f97\u7269" in payload["official_sources_summary"]
    assert "\u76d2\u9a6c" in payload["official_sources_summary"]
    assert "\u7c73\u54c8\u6e38" in payload["official_sources_summary"]
    assert payload["openai_api_key_configured"] is False
    assert payload["openai_api_key_preview"] is None


def test_runtime_config_can_be_updated(client):
    response = client.put(
        "/api/runtime-config",
        json={
            "llm_provider": "openai_compatible",
            "openai_base_url": "https://example.com/v1",
            "openai_model": "gpt-4o-mini",
            "openai_api_key": "secret-key-123456",
            "replace_api_key": True,
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["llm_provider"] == "openai_compatible"
    assert payload["openai_base_url"] == "https://example.com/v1"
    assert payload["openai_model"] == "gpt-4o-mini"
    assert payload["openai_api_key_configured"] is True
    assert payload["openai_api_key_preview"] != "secret-key-123456"
    assert payload["llm_effective_provider"] == "openai_compatible"
    assert runtime_config_service.config_path.exists()


def test_runtime_llm_probe_endpoints(client, monkeypatch):
    async def fake_list_models(config):
        assert config.openai_base_url == "https://example.com/v1"
        assert config.openai_model is None
        return ["gpt-4o-mini", "gpt-4.1-mini"]

    async def fake_test_connection(config):
        assert config.openai_api_key == "secret-key-123456"
        return {"latency_ms": 123, "reply_preview": "OK"}

    monkeypatch.setattr(runtime_config_service, "list_models", fake_list_models)
    monkeypatch.setattr(runtime_config_service, "test_connection", fake_test_connection)

    update = client.put(
        "/api/runtime-config",
        json={
            "llm_provider": "openai_compatible",
            "openai_base_url": "https://example.com/v1",
            "openai_model": None,
            "openai_api_key": "secret-key-123456",
            "replace_api_key": True,
        },
    )
    assert update.status_code == 200

    models = client.post(
        "/api/runtime-config/llm/models",
        json={"llm_provider": "openai_compatible"},
    )
    assert models.status_code == 200
    assert models.json()["models"] == ["gpt-4o-mini", "gpt-4.1-mini"]

    probe = client.post(
        "/api/runtime-config/llm/test",
        json={
            "llm_provider": "openai_compatible",
            "openai_model": "gpt-4o-mini",
        },
    )
    assert probe.status_code == 200
    assert probe.json()["ok"] is True
    assert probe.json()["latency_ms"] == 123
    assert probe.json()["reply_preview"] == "OK"


def test_resume_upload_persists_enriched_profile_fields(client, monkeypatch):
    monkeypatch.setattr(
        profile_module,
        "_read_docx",
        lambda _path: "\n".join(
            [
                "Jane Doe",
                "Senior Frontend Engineer",
                "Projects",
                "Search Console Rebuild",
                "Role: Lead Engineer",
                "Built a React TypeScript search console with FastAPI ranking services",
                "Awards",
                "Open Source Award",
                "Issuer: Community Summit",
                "Won first place in 2024",
                "Skills",
                "React, TypeScript, FastAPI",
            ]
        ),
    )

    response = client.post(
        "/api/resume/upload",
        files={
            "file": (
                "resume.docx",
                b"fake-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["raw_text"]
    assert "React" in payload["tech_stack"]
    assert payload["project_experiences"]
    assert payload["project_experiences"][0]["name"] == "Search Console Rebuild"
    assert payload["awards"]
    assert payload["awards"][0]["title"] == "Open Source Award"


def test_resume_upload_falls_back_when_profile_enhancement_fails(client, monkeypatch):
    monkeypatch.setattr(profile_module, "_read_docx", lambda _path: "Jane\nProjects\nResume Search\nReact")
    monkeypatch.setattr(
        profile_service,
        "_enhance_profile_fields",
        lambda _update: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.post(
        "/api/resume/upload",
        files={
            "file": (
                "resume.docx",
                b"fake-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tech_stack"]
    assert payload["project_experiences"]


def test_search_pipeline_marks_ready_before_background_llm_finishes(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    async def fake_analyze_jobs(db, profile, jobs):
        await asyncio.sleep(0.5)
        job_list = list(jobs)
        return AnalysisBatch(
            metadata=AnalysisMetadata(
                provider="heuristic",
                degraded=True,
                notice="background analysis complete",
            ),
            results=[
                LLMResult(
                    cache_key=f"cache-{job.job_id}",
                    job_id=job.job_id,
                    llm_score=88.0,
                    highlights=["React"],
                    missing_keywords=[],
                    risk_flags=[],
                    llm_summary="ranked",
                )
                for job in job_list
            ],
        )

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(llm_service, "analyze_jobs", fake_analyze_jobs)

    session = create_search_session(client)
    assert session.status_code == 200

    ready = wait_for_session_status(client, session.json()["id"], "ready")
    assert ready["analysis_status"] in {"pending", "running"}
    assert ready["analysis_degraded"] is False

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    payload = matches.json()
    assert len(payload) == 1
    assert payload[0]["platform"] == "official"
    assert payload[0]["apply_supported"] is True
    assert payload[0]["listing_id"]
    assert payload[0]["job_id"] == "official-live-001"
    assert payload[0]["source_company"] == "ByteDance"
    assert payload[0]["description_text"]
    assert payload[0]["llm_score"] is None
    assert payload[0]["analysis_degraded"] is False

    enriched = wait_for_analysis_status(client, session.json()["id"], "ready")
    assert enriched["analysis_provider"] == "heuristic"
    assert enriched["analysis_degraded"] is True
    assert enriched["analysis_notice"] == "background analysis complete"

    enriched_matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert enriched_matches.status_code == 200
    enriched_payload = enriched_matches.json()
    assert enriched_payload[0]["llm_score"] == 88.0
    assert enriched_payload[0]["analysis_degraded"] is True


def test_search_pipeline_records_stage_timings_in_session_meta(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return sample_drafts(10)

    async def fake_analyze_jobs(db, profile, jobs):
        await asyncio.sleep(0.2)
        job_list = list(jobs)
        return AnalysisBatch(
            metadata=AnalysisMetadata(
                provider="heuristic",
                degraded=True,
                notice="timed",
            ),
            results=[
                LLMResult(
                    cache_key=f"cache-{job.job_id}",
                    job_id=job.job_id,
                    llm_score=77.0,
                    highlights=["React"],
                    missing_keywords=[],
                    risk_flags=[],
                    llm_summary="timed",
                )
                for job in job_list
            ],
        )

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(llm_service, "analyze_jobs", fake_analyze_jobs)

    session = create_search_session(client, salary_floor=0, must_have_keywords=[], cities=[])
    assert session.status_code == 200
    session_id = session.json()["id"]

    wait_for_session_status(client, session_id, "ready")
    wait_for_analysis_status(client, session_id, "ready")

    with Session(db_module.engine) as db:
        setting = db.get(AppSetting, search_service._session_meta_key(session_id))
        assert setting is not None
        meta = dict(setting.value or {})

    assert isinstance(meta.get("fetch_ms"), int)
    assert isinstance(meta.get("rule_rank_ms"), int)
    assert isinstance(meta.get("persist_ms"), int)
    assert isinstance(meta.get("time_to_ready_ms"), int)
    assert isinstance(meta.get("llm_ms"), int)
    assert isinstance(meta.get("time_to_llm_enriched_ms"), int)
    assert meta["time_to_llm_enriched_ms"] >= meta["time_to_ready_ms"]


def test_search_matches_merge_same_job_id_with_multi_locations(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            variant_draft(
                job_id="official-dup-001",
                location_city="Hangzhou",
                apply_suffix="hangzhou",
            ),
            variant_draft(
                job_id="official-dup-001",
                location_city="Beijing",
                apply_suffix="beijing",
            ),
            variant_draft(
                job_id="official-dup-001",
                location_city="Shanghai",
                apply_suffix="shanghai",
            ),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client, salary_floor=0, must_have_keywords=[], cities=[])
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 1
    match = payload[0]
    assert match["job_id"] == "official-dup-001"
    assert match["is_merged"] is True
    assert match["merged_count"] == 3
    assert set(match["location_cities"]) == {"Hangzhou", "Beijing", "Shanghai"}
    assert set(match["location_display"].split("/")) == {
        "Hangzhou",
        "Beijing",
        "Shanghai",
    }
    assert len(match["location_options"]) == 3
    assert set(item["location_city"] for item in match["location_options"]) == {
        "Hangzhou",
        "Beijing",
        "Shanghai",
    }
    assert any(match["apply_url"].endswith(suffix) for suffix in ["/hangzhou", "/beijing", "/shanghai"])


def test_search_matches_do_not_merge_when_job_id_differs(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            variant_draft(
                job_id="official-uniq-001",
                location_city="Hangzhou",
                apply_suffix="hz",
                title="Frontend Engineer Platform A",
            ),
            variant_draft(
                job_id="official-uniq-002",
                location_city="Beijing",
                apply_suffix="bj",
                title="Frontend Engineer Platform B",
            ),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client, salary_floor=0, must_have_keywords=[], cities=[])
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 2
    assert all(item["is_merged"] is False for item in payload)
    assert all(item["merged_count"] == 1 for item in payload)
    assert {item["job_id"] for item in payload} == {"official-uniq-001", "official-uniq-002"}


def test_search_matches_merge_by_heuristic_when_job_ids_differ(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        shared_description = (
            "负责小荷健康业务前端系统建设，参与复杂数据流与组件化架构设计，"
            "推进性能优化与工程化体系建设，保障跨端一致性与可维护性。"
        )
        return [
            variant_draft(
                job_id="jd-a-001",
                location_city="Shenzhen",
                apply_suffix="sz",
                title="大模型应用研发工程师-小荷健康",
                description_text=shared_description,
                requirements_text="熟悉 Linux，掌握常用数据结构与算法，具备扎实工程能力。",
                employment_type="Experienced",
            ),
            variant_draft(
                job_id="jd-b-002",
                location_city="Beijing",
                apply_suffix="bj",
                title="大模型应用研发工程师-小荷健康",
                description_text=shared_description,
                requirements_text="熟悉 Linux，掌握常用数据结构与算法，具备扎实工程能力。",
                employment_type="Experienced",
            ),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client, salary_floor=0, must_have_keywords=[], cities=[])
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 1
    assert payload[0]["is_merged"] is True
    assert payload[0]["merged_count"] == 2
    assert set(payload[0]["location_cities"]) == {"Shenzhen", "Beijing"}


def test_search_matches_do_not_merge_same_title_when_content_differs(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            variant_draft(
                job_id="jd-c-001",
                location_city="Shanghai",
                apply_suffix="sh",
                title="前端开发工程师-国际支付",
                description_text="负责支付前端系统搭建，聚焦交易流程与资金安全体验优化。",
                requirements_text="熟练掌握 JavaScript、TypeScript、React。",
                employment_type="Internship",
            ),
            variant_draft(
                job_id="jd-d-002",
                location_city="Beijing",
                apply_suffix="bj",
                title="前端开发工程师-国际支付",
                description_text="负责广告增长平台的投放链路建设，聚焦策略实验与报表分析能力。",
                requirements_text="熟练掌握 Vue、数据可视化与埋点体系建设。",
                employment_type="Internship",
            ),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client, salary_floor=0, must_have_keywords=[], cities=[])
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 2
    assert all(item["is_merged"] is False for item in payload)
    assert all(item["merged_count"] == 1 for item in payload)


def test_search_matches_do_not_merge_when_job_id_is_empty(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            variant_draft(job_id="", location_city="Hangzhou", apply_suffix="hz-empty"),
            variant_draft(job_id="", location_city="Beijing", apply_suffix="bj-empty"),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client, salary_floor=0, must_have_keywords=[], cities=[])
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 2
    assert all(item["job_id"] == "" for item in payload)
    assert all(item["is_merged"] is False for item in payload)
    assert all(item["merged_count"] == 1 for item in payload)


def test_search_matches_keep_representative_score_order_after_merge(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            variant_draft(
                job_id="low-score",
                title="Backend Engineer",
                location_city="Beijing",
                apply_suffix="bj",
            ),
            variant_draft(
                job_id="low-score",
                title="Backend Engineer",
                location_city="Shanghai",
                apply_suffix="sh",
            ),
            variant_draft(
                job_id="high-score",
                title="Senior Frontend Engineer",
                location_city="Hangzhou",
                apply_suffix="hz",
            ),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client, salary_floor=0, must_have_keywords=[], cities=[])
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 2
    assert payload[0]["job_id"] == "high-score"
    assert payload[1]["job_id"] == "low-score"


def test_guided_apply_requires_consent_and_uses_listing_id(client, monkeypatch):
    upsert_profile(client, with_resume=True)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client, mode="guided_apply")
    assert session.status_code == 403

    client.post(
        "/api/risk-consents",
        json={"consent_type": "guided_apply", "platform": "official", "version": "1.0.0"},
    )
    session = create_search_session(client, mode="guided_apply")
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    listing_id = client.get(f"/api/search-sessions/{session.json()['id']}/matches").json()[0]["listing_id"]
    attempt = client.post(f"/api/jobs/{listing_id}/guided-apply")
    assert attempt.status_code == 200
    assert attempt.json()["status"] == "needs_verification"
    assert attempt.json()["listing_id"] == listing_id

    verification = client.post(
        f"/api/application-attempts/{attempt.json()['id']}/open-verification-window"
    )
    assert verification.status_code == 200
    assert "验证码" in verification.json()["message"]

    continued = client.post(f"/api/application-attempts/{attempt.json()['id']}/continue")
    assert continued.status_code == 200
    assert continued.json()["status"] == "prepared"


def test_blocked_search_can_open_verification_and_retry(client, monkeypatch):
    upsert_profile(client)
    call_count = {"value": 0}

    async def fake_search_jobs(search, profile):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise PlatformBlockedError(
                "Manual verification required.",
                verification_url="https://example.com/verify",
            )
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client)
    assert session.status_code == 200

    blocked = wait_for_session_status(client, session.json()["id"], "blocked")
    assert blocked["blocked_reason"] == "Manual verification required."

    reopen = client.post(f"/api/search-sessions/{session.json()['id']}/open-verification")
    assert reopen.status_code == 200
    assert reopen.json()["url"] == "https://example.com/verify"

    retry = client.post(f"/api/search-sessions/{session.json()['id']}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "running"

    ready = wait_for_session_status(client, session.json()["id"], "ready")
    assert ready["blocked_reason"] is None
    assert call_count["value"] == 2


def test_search_session_persists_source_filters_and_retry_reuses_them(client, monkeypatch):
    upsert_profile(client)
    observed: list[tuple[list[str], list[str]]] = []

    async def fake_search_jobs(search, profile):
        observed.append((list(search.source_variants), list(search.source_companies)))
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        source_variants=["campus", "internship"],
        source_companies=["字节跳动"],
        force_refresh=True,
    )
    assert session.status_code == 200
    session_id = session.json()["id"]
    wait_for_session_status(client, session_id, "ready")

    latest = client.get(f"/api/search-sessions/{session_id}")
    assert latest.status_code == 200
    payload = latest.json()
    assert payload["source_variants"] == ["campus", "internship"]
    assert payload["source_companies"] == ["字节跳动"]
    assert payload["force_refresh"] is True

    retry = client.post(f"/api/search-sessions/{session_id}/retry")
    assert retry.status_code == 200
    wait_for_session_status(client, session_id, "ready")

    assert len(observed) >= 2
    assert observed[0] == (["campus", "internship"], ["字节跳动"])
    assert observed[1] == (["campus", "internship"], ["字节跳动"])


def test_search_session_persists_limits_and_retry_reuses_them(client, monkeypatch):
    upsert_profile(client)
    observed: list[tuple[int, int]] = []

    async def fake_search_jobs(search, profile):
        observed.append((search.match_limit, search.company_job_limit))
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        match_limit=150,
        company_job_limit=40,
        force_refresh=True,
    )
    assert session.status_code == 200
    session_id = session.json()["id"]
    wait_for_session_status(client, session_id, "ready")

    latest = client.get(f"/api/search-sessions/{session_id}")
    assert latest.status_code == 200
    payload = latest.json()
    assert payload["match_limit"] == 150
    assert payload["company_job_limit"] == 40

    retry = client.post(f"/api/search-sessions/{session_id}/retry")
    assert retry.status_code == 200
    wait_for_session_status(client, session_id, "ready")

    assert observed[0] == (150, 40)
    assert observed[1] == (150, 40)


def test_search_fetch_cache_hit_reuses_previous_payload(client, monkeypatch):
    upsert_profile(client)
    call_count = {"value": 0}

    async def fake_search_jobs(search, profile):
        call_count["value"] += 1
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    first = create_search_session(client, cities=[], salary_floor=0, must_have_keywords=[])
    assert first.status_code == 200
    wait_for_session_status(client, first.json()["id"], "ready")
    first_matches = client.get(f"/api/search-sessions/{first.json()['id']}/matches").json()

    second = create_search_session(client, cities=[], salary_floor=0, must_have_keywords=[])
    assert second.status_code == 200
    wait_for_session_status(client, second.json()["id"], "ready")
    second_matches = client.get(f"/api/search-sessions/{second.json()['id']}/matches").json()

    assert call_count["value"] == 1
    assert len(first_matches) == 1
    assert len(second_matches) == 1
    assert first_matches[0]["job_id"] == second_matches[0]["job_id"]
    assert first_matches[0]["title"] == second_matches[0]["title"]
    assert first_matches[0]["location_city"] == second_matches[0]["location_city"]
    assert first_matches[0]["apply_url"] == second_matches[0]["apply_url"]

    with Session(db_module.engine) as db:
        cache_row = db.exec(select(SearchFetchCache)).first()
        assert cache_row is not None
        assert cache_row.hit_count >= 1


def test_search_fetch_cache_key_changes_with_profile_keyword_basis(client, monkeypatch):
    upsert_profile(client)
    call_count = {"value": 0}

    async def fake_search_jobs(search, profile):
        call_count["value"] += 1
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    first = create_search_session(client, cities=[], salary_floor=0, must_have_keywords=[])
    assert first.status_code == 200
    wait_for_session_status(client, first.json()["id"], "ready")

    current_profile = client.get("/api/profile").json()
    current_profile["tech_stack"] = ["Kubernetes", "Go", "Docker"]
    update = client.put("/api/profile", json=current_profile)
    assert update.status_code == 200

    second = create_search_session(client, cities=[], salary_floor=0, must_have_keywords=[])
    assert second.status_code == 200
    wait_for_session_status(client, second.json()["id"], "ready")

    assert call_count["value"] == 2
    with Session(db_module.engine) as db:
        cache_rows = db.exec(select(SearchFetchCache)).all()
        assert len(cache_rows) == 2
        assert any("Kubernetes" in row.keyword_basis for row in cache_rows)


def test_search_fetch_cache_force_refresh_bypasses_cache(client, monkeypatch):
    upsert_profile(client)
    call_count = {"value": 0}

    async def fake_search_jobs(search, profile):
        call_count["value"] += 1
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    first = create_search_session(client, cities=[], salary_floor=0, must_have_keywords=[])
    assert first.status_code == 200
    wait_for_session_status(client, first.json()["id"], "ready")

    second = create_search_session(
        client,
        cities=[],
        salary_floor=0,
        must_have_keywords=[],
        force_refresh=True,
    )
    assert second.status_code == 200
    wait_for_session_status(client, second.json()["id"], "ready")

    assert call_count["value"] == 2
    detail = client.get(f"/api/search-sessions/{second.json()['id']}").json()
    assert detail["force_refresh"] is True


def test_llm_cache_key_changes_with_profile_signature(client):
    profile_one = client.put(
        "/api/profile",
        json={
            "id": 1,
            "full_name": "Candidate A",
            "headline": "Frontend Engineer",
            "summary": "React profile",
            "target_roles": ["Frontend Engineer"],
            "preferred_cities": ["Shanghai"],
            "salary_floor": 20000,
            "years_experience": 5,
            "degree": "Bachelor",
            "skills": ["React", "TypeScript"],
            "must_have_keywords": ["React"],
            "tech_stack": ["React", "TypeScript"],
            "project_experiences": [],
            "awards": [],
            "source_filename": None,
            "source_language": "en",
            "raw_text": "React TypeScript",
        },
    ).json()
    profile_two = {**profile_one, "tech_stack": ["Go", "Docker"]}
    job = JobListing(
        session_id="session-1",
        platform="official",
        source_company="ByteDance",
        source_site="jobs.bytedance.com",
        job_id="job-1",
        title="Frontend Engineer",
        description_text="React TypeScript role",
        requirements_text="React experience required",
    )

    with Session(db_module.engine) as db:
        first = asyncio.run(
            llm_service.analyze_jobs(
                db,
                CandidateProfile.model_validate(profile_one),
                [job],
            )
        )
        second = asyncio.run(
            llm_service.analyze_jobs(
                db,
                CandidateProfile.model_validate(profile_two),
                [job],
            )
        )

    assert first.results[0].cache_key != second.results[0].cache_key


def test_search_fetch_cache_expires_and_refetches(client, monkeypatch):
    upsert_profile(client)
    call_count = {"value": 0}

    async def fake_search_jobs(search, profile):
        call_count["value"] += 1
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    first = create_search_session(client, cities=[], salary_floor=0, must_have_keywords=[])
    assert first.status_code == 200
    wait_for_session_status(client, first.json()["id"], "ready")

    with Session(db_module.engine) as db:
        cache_row = db.exec(select(SearchFetchCache)).first()
        assert cache_row is not None
        cache_row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.add(cache_row)
        db.commit()

    second = create_search_session(client, cities=[], salary_floor=0, must_have_keywords=[])
    assert second.status_code == 200
    wait_for_session_status(client, second.json()["id"], "ready")

    assert call_count["value"] == 2


def test_search_pipeline_is_not_capped_to_twenty_matches(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return sample_drafts(35)

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
    )
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    assert len(matches.json()) == 35


def test_search_pipeline_only_applies_llm_to_first_120_matches(client, monkeypatch):
    upsert_profile(client)
    observed = {"jobs": 0}

    async def fake_search_jobs(search, profile):
        return sample_drafts(130)

    async def fake_analyze_jobs(db, profile, jobs):
        job_list = list(jobs)
        observed["jobs"] = len(job_list)
        return AnalysisBatch(
            metadata=AnalysisMetadata(
                provider="heuristic",
                degraded=True,
                notice="test",
            ),
            results=[
                LLMResult(
                    cache_key=f"cache-{job.job_id}",
                    job_id=job.job_id,
                    llm_score=88.0,
                    highlights=["React"],
                    missing_keywords=[],
                    risk_flags=[],
                    llm_summary="ok",
                )
                for job in job_list
            ],
        )

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(llm_service, "analyze_jobs", fake_analyze_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
    )
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    wait_for_analysis_status(client, session.json()["id"], "ready")
    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200

    payload = matches.json()
    assert len(payload) == 130
    assert observed["jobs"] == 120
    assert sum(1 for item in payload if item["llm_score"] is not None) == 120
    assert sum(1 for item in payload if item["llm_score"] is None) == 10


def test_search_pipeline_soft_diversity_spreads_top_companies(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            company_draft(job_id="a-1", source_company="ByteDance"),
            company_draft(job_id="a-2", source_company="ByteDance"),
            company_draft(job_id="a-3", source_company="ByteDance"),
            company_draft(job_id="jd-1", source_company="JD"),
            company_draft(job_id="mt-1", source_company="Meituan"),
            company_draft(job_id="a-4", source_company="ByteDance"),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
        match_limit=6,
        company_job_limit=6,
    )
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert [item["source_company"] for item in payload[:3]] == [
        "ByteDance",
        "JD",
        "Meituan",
    ]
    by_job_id = {item["job_id"]: item for item in payload}
    assert by_job_id["a-1"]["final_score"] - by_job_id["a-2"]["final_score"] == 8.0
    assert payload[0]["final_score"] > payload[3]["final_score"]


def test_search_matches_order_is_stable_when_diversity_scores_tie(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            company_draft(job_id="a-1", source_company="ByteDance"),
            company_draft(job_id="a-2", source_company="ByteDance"),
            company_draft(job_id="jd-1", source_company="JD"),
            company_draft(job_id="mt-1", source_company="Meituan"),
            company_draft(job_id="jd-2", source_company="JD"),
            company_draft(job_id="mt-2", source_company="Meituan"),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
        match_limit=6,
        company_job_limit=6,
    )
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    first = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    second = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert first.status_code == 200
    assert second.status_code == 200

    first_order = [item["job_id"] for item in first.json()]
    second_order = [item["job_id"] for item in second.json()]
    assert first_order == second_order


def test_search_pipeline_caps_visible_matches_to_200(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return sample_drafts(230)

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
    )
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    payload = matches.json()

    assert len(payload) == 200
    assert payload[0]["job_id"] == "official-live-000"
    assert payload[-1]["job_id"] == "official-live-199"


def test_search_pipeline_caps_matches_per_company(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        drafts = sample_drafts(90)
        for index, draft in enumerate(drafts):
            draft.source_company = "ByteDance" if index < 60 else "JD"
        return drafts

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
        match_limit=50,
        company_job_limit=10,
    )
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    payload = matches.json()

    assert len(payload) == 20
    counts: dict[str, int] = {}
    for item in payload:
        counts[item["source_company"]] = counts.get(item["source_company"], 0) + 1
    assert counts == {"ByteDance": 10, "JD": 10}


def test_search_pipeline_soft_diversity_respects_company_cap(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            company_draft(job_id=f"a-{index}", source_company="ByteDance")
            for index in range(1, 7)
        ] + [
            company_draft(job_id=f"jd-{index}", source_company="JD")
            for index in range(1, 3)
        ] + [
            company_draft(job_id=f"mt-{index}", source_company="Meituan")
            for index in range(1, 3)
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
        match_limit=6,
        company_job_limit=2,
    )
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 6
    counts: dict[str, int] = {}
    for item in payload:
        counts[item["source_company"]] = counts.get(item["source_company"], 0) + 1
    assert counts == {"ByteDance": 2, "JD": 2, "Meituan": 2}
    assert [item["source_company"] for item in payload[:3]] == [
        "ByteDance",
        "JD",
        "Meituan",
    ]


def test_search_pipeline_recomputes_diversity_scores_after_llm_enrichment(
    client, monkeypatch
):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [
            company_draft(job_id="a-1", source_company="ByteDance"),
            company_draft(job_id="a-2", source_company="ByteDance"),
            company_draft(job_id="jd-1", source_company="JD"),
            company_draft(job_id="mt-1", source_company="Meituan"),
        ]

    async def fake_analyze_jobs(db, profile, jobs):
        await asyncio.sleep(0.5)
        llm_scores = {
            "a-1": 80.0,
            "a-2": 100.0,
            "jd-1": 65.0,
            "mt-1": 60.0,
        }
        return AnalysisBatch(
            metadata=AnalysisMetadata(
                provider="heuristic",
                degraded=True,
                notice="llm reranked",
            ),
            results=[
                LLMResult(
                    cache_key=f"cache-{job.job_id}",
                    job_id=job.job_id,
                    llm_score=llm_scores[job.job_id],
                    highlights=["React"],
                    missing_keywords=[],
                    risk_flags=[],
                    llm_summary="reranked",
                )
                for job in jobs
            ],
        )

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(llm_service, "analyze_jobs", fake_analyze_jobs)

    session = create_search_session(
        client,
        salary_floor=0,
        must_have_keywords=[],
        cities=[],
        match_limit=4,
        company_job_limit=4,
    )
    assert session.status_code == 200
    session_id = session.json()["id"]

    wait_for_session_status(client, session_id, "ready")
    initial = client.get(f"/api/search-sessions/{session_id}/matches")
    assert initial.status_code == 200
    initial_payload = initial.json()
    initial_order = [item["job_id"] for item in initial_payload]
    initial_scores = {item["job_id"]: item["final_score"] for item in initial_payload}

    assert initial_order == ["a-1", "jd-1", "mt-1", "a-2"]

    wait_for_analysis_status(client, session_id, "ready")
    enriched = client.get(f"/api/search-sessions/{session_id}/matches")
    assert enriched.status_code == 200
    enriched_payload = enriched.json()
    enriched_order = [item["job_id"] for item in enriched_payload]
    enriched_scores = {item["job_id"]: item["final_score"] for item in enriched_payload}

    assert enriched_order == ["a-2", "jd-1", "a-1", "mt-1"]
    assert enriched_scores["a-2"] > initial_scores["a-2"]
    assert enriched_scores["a-2"] > enriched_scores["jd-1"]
    assert enriched_scores["jd-1"] > enriched_scores["a-1"]
    assert enriched_payload[0]["llm_score"] == 100.0
    assert enriched_payload[0]["analysis_notice"] == "llm reranked"


def test_background_llm_failure_does_not_roll_back_ready_session(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    async def fake_analyze_jobs(db, profile, jobs):
        await asyncio.sleep(0.2)
        raise RuntimeError("background llm crashed")

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(llm_service, "analyze_jobs", fake_analyze_jobs)

    session = create_search_session(client)
    assert session.status_code == 200

    ready = wait_for_session_status(client, session.json()["id"], "ready")
    assert ready["analysis_status"] in {"pending", "running"}

    failed = wait_for_analysis_status(client, session.json()["id"], "failed")
    assert failed["status"] == "ready"
    assert failed["analysis_degraded"] is True
    assert "background llm crashed" in (failed["analysis_notice"] or "")

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    payload = matches.json()
    assert len(payload) == 1
    assert payload[0]["llm_score"] is None


def test_disabled_platform_is_rejected(client):
    upsert_profile(client)
    response = create_search_session(client, platforms=["boss"])
    assert response.status_code == 409
    assert "未启用 Boss" in response.json()["detail"]


def test_openai_failure_falls_back_to_heuristic(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    async def fake_analyze(self, profile, jobs):
        raise RuntimeError("model backend unavailable")

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)
    monkeypatch.setattr(OpenAICompatibleLLMProvider, "analyze", fake_analyze)

    update = client.put(
        "/api/runtime-config",
        json={
            "llm_provider": "openai_compatible",
            "openai_base_url": "https://example.com/v1",
            "openai_model": "gpt-4o-mini",
            "openai_api_key": "secret-key-123456",
            "replace_api_key": True,
        },
    )
    assert update.status_code == 200

    session = create_search_session(client)
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")
    enriched = wait_for_analysis_status(client, session.json()["id"], "ready")
    assert enriched["analysis_degraded"] is True
    assert "LLM" in (enriched["analysis_notice"] or "")

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    assert len(matches.json()) == 1


def test_official_adapter_extends_keywords_with_top_profile_tech_terms(client, monkeypatch):
    upsert_profile(client)
    observed: dict[str, list[str]] = {}

    async def fake_run(sources, search, profile):
        observed["keywords"] = list(search.job_targets)
        return []

    monkeypatch.setattr(career_collector_runner, "run", fake_run)

    with Session(db_module.engine) as db:
        profile = profile_service.load_or_create(db)
    try:
        asyncio.run(
            official_adapter.search_jobs(
                SearchSessionCreate(
                    platforms=["official"],
                    mode="recommend_only",
                    job_targets=["Frontend Engineer", "Platform Engineer"],
                    cities=[],
                    salary_floor=0,
                    must_have_keywords=[],
                    source_variants=[],
                    source_companies=[],
                    force_refresh=False,
                ),
                profile,
            )
        )
    except Exception:
        pass

    assert observed["keywords"] == [
        "Frontend Engineer",
        "Platform Engineer",
        "React",
        "TypeScript",
        "Node.js",
    ]
