import time

from openresume_api.adapters.base import NormalizedJobDraft, PlatformBlockedError
from openresume_api.adapters.official import official_adapter
from openresume_api.services.llm import OpenAICompatibleLLMProvider
from openresume_api.services.runtime_config import runtime_config_service


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
):
    return client.post(
        "/api/search-sessions",
        json={
            "platforms": platforms or ["official"],
            "mode": mode,
            "job_targets": ["Frontend Engineer", "Full Stack Engineer"],
            "cities": ["Shanghai", "Hangzhou"],
            "salary_floor": 25000,
            "must_have_keywords": ["React", "TypeScript"],
        },
    )


def sample_draft() -> NormalizedJobDraft:
    return NormalizedJobDraft(
        external_job_id="official-live-001",
        title="Senior Frontend Engineer",
        company_name="Example Corp",
        city="Shanghai",
        salary_text="25K-35K",
        salary_min=25000,
        salary_max=35000,
        experience_text="3-5 years",
        degree_text="Bachelor",
        work_mode="onsite",
        url="https://example.com/jobs/official-live-001",
        detail_url="https://example.com/jobs/official-live-001",
        apply_url="https://example.com/jobs/official-live-001/apply",
        source_company_url="https://example.com/careers",
        apply_requires_login=True,
        jd_text="React TypeScript Electron FastAPI official site flow",
        jd_hash="official-live-001-hash",
        raw_payload={"source": "test", "platform": "official"},
    )


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
    assert "archive/boss-login" in payload[1]["disabled_reason"]


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
    assert payload["official_source_file"].endswith("url.md")
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
    assert payload[0]["analysis_degraded"] is True


def test_guided_apply_requires_consent_and_can_continue_after_popup(client, monkeypatch):
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

    job_id = client.get(f"/api/search-sessions/{session.json()['id']}/matches").json()[0]["job_id"]
    attempt = client.post(f"/api/jobs/{job_id}/guided-apply")
    assert attempt.status_code == 200
    assert attempt.json()["status"] == "needs_verification"

    verification = client.post(
        f"/api/application-attempts/{attempt.json()['id']}/open-verification-window"
    )
    assert verification.status_code == 200
    assert verification.json()["url"].endswith("/apply")

    continued = client.post(
        f"/api/application-attempts/{attempt.json()['id']}/continue"
    )
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


def test_disabled_platform_is_rejected(client):
    upsert_profile(client)
    response = create_search_session(client, platforms=["boss"])
    assert response.status_code == 409
    assert "archive/boss-login" in response.json()["detail"]


def test_openai_failure_does_not_fallback_to_heuristic(client, monkeypatch):
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

    failed = wait_for_session_status(client, session.json()["id"], "failed")
    assert "model backend unavailable" in failed["summary"]

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    assert matches.json() == []
