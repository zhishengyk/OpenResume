import time
from datetime import datetime, timedelta

from openresume_api import db as db_module
from openresume_api.adapters.base import NormalizedJobDraft, PlatformBlockedError
from openresume_api.adapters.official import official_adapter
from openresume_api.models import SearchFetchCache
from openresume_api.services.llm import (
    AnalysisBatch,
    AnalysisMetadata,
    LLMResult,
    OpenAICompatibleLLMProvider,
    llm_service,
)
from openresume_api.services.runtime_config import runtime_config_service
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
            "source_filename": "resume.pdf" if with_resume else None,
            "source_language": "zh-CN",
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
    assert payload["official_sources_summary"] == "代码清单：字节跳动社招 + 校招 + 实习"
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


def test_search_pipeline_returns_matches_and_degraded_notice(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client)
    assert session.status_code == 200

    ready = wait_for_session_status(client, session.json()["id"], "ready")
    assert ready["analysis_degraded"] is True
    assert ready["analysis_provider"] == "heuristic"

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
    assert payload[0]["analysis_degraded"] is True


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
    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200

    payload = matches.json()
    assert len(payload) == 130
    assert observed["jobs"] == 120
    assert sum(1 for item in payload if item["llm_score"] is not None) == 120
    assert sum(1 for item in payload if item["llm_score"] is None) == 10


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

    ready = wait_for_session_status(client, session.json()["id"], "ready")
    assert ready["analysis_degraded"] is True
    assert "LLM 调用失败" in (ready["analysis_notice"] or "")

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    assert len(matches.json()) == 1
