import time

from openresume_api.adapters.base import NormalizedJobDraft, PlatformBlockedError
from openresume_api.adapters.demo import demo_adapter


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


def upsert_profile(client):
    response = client.put(
        "/api/profile",
        json={
            "id": 1,
            "full_name": "Test Candidate",
            "headline": "Senior Frontend Engineer",
            "summary": "React and TypeScript engineer",
            "target_roles": ["前端工程师", "全栈工程师"],
            "preferred_cities": ["上海", "杭州"],
            "salary_floor": 25000,
            "years_experience": 5,
            "degree": "本科",
            "skills": ["React", "TypeScript", "Node.js", "FastAPI"],
            "must_have_keywords": ["React", "TypeScript"],
            "source_filename": None,
            "source_language": "zh-CN",
        },
    )
    assert response.status_code == 200


def create_search_session(
    client,
    *,
    platform: str = "demo",
    mode: str = "recommend_only",
):
    return client.post(
        "/api/search-sessions",
        json={
            "platform": platform,
            "mode": mode,
            "job_targets": ["前端工程师", "全栈工程师"],
            "cities": ["上海", "杭州"],
            "salary_floor": 25000,
            "must_have_keywords": ["React", "TypeScript"],
        },
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


def test_platform_registry_is_modular(client):
    response = client.get("/api/platforms")
    assert response.status_code == 200
    payload = response.json()

    assert [item["platform"] for item in payload] == ["demo", "liepin"]

    demo = payload[0]
    assert demo["search_supported"] is True
    assert demo["session_supported"] is False
    assert demo["session_required"] is False


def test_search_pipeline_returns_matches(client):
    upsert_profile(client)

    session = create_search_session(client)
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    payload = matches.json()
    assert len(payload) >= 1
    assert payload[0]["final_score"] >= payload[0]["rule_score"] * 0.6


def test_guided_apply_requires_consent_and_respects_emergency_stop(client):
    upsert_profile(client)
    session = create_search_session(client)
    assert session.status_code == 200
    wait_for_session_status(client, session.json()["id"], "ready")

    job_id = client.get(f"/api/search-sessions/{session.json()['id']}/matches").json()[0]["job_id"]
    no_consent = client.post(f"/api/jobs/{job_id}/guided-apply")
    assert no_consent.status_code == 403

    client.post(
        "/api/risk-consents",
        json={"consent_type": "guided_apply", "platform": "demo", "version": "1.0.0"},
    )
    client.post("/api/emergency-stop", json={"active": True})
    blocked = client.post(f"/api/jobs/{job_id}/guided-apply")
    assert blocked.status_code == 409


def test_blocked_search_can_open_verification_and_retry(client, monkeypatch):
    upsert_profile(client)
    call_count = {"value": 0}

    async def fake_search_jobs(search, profile):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise PlatformBlockedError(
                "需要人工验证。",
                verification_url="https://example.com/verify",
            )
        return [
            NormalizedJobDraft(
                external_job_id="demo-live-001",
                title="资深前端工程师",
                company_name="示例公司",
                city="上海·浦东",
                salary_text="25K-35K·14薪",
                salary_min=25000,
                salary_max=35000,
                experience_text="3-5年",
                degree_text="本科",
                work_mode="onsite",
                url="https://example.com/jobs/demo-live-001",
                jd_text="React TypeScript Electron FastAPI",
                jd_hash="demo-live-001-hash",
                raw_payload={"source": "test"},
            )
        ]

    monkeypatch.setattr(demo_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client)
    assert session.status_code == 200

    blocked = wait_for_session_status(client, session.json()["id"], "blocked")
    assert blocked["blocked_reason"] == "需要人工验证。"
    assert "验证" in blocked["summary"]

    reopen = client.post(f"/api/search-sessions/{session.json()['id']}/open-verification")
    assert reopen.status_code == 200

    retry = client.post(f"/api/search-sessions/{session.json()['id']}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "running"

    ready = wait_for_session_status(client, session.json()["id"], "ready")
    assert ready["blocked_reason"] is None

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    payload = matches.json()
    assert len(payload) == 1
    assert payload[0]["url"].endswith("/demo-live-001")
    assert call_count["value"] == 2


def test_session_routes_reject_modules_without_session_support(client):
    response = client.post("/api/platforms/demo/session/start")
    assert response.status_code == 409


def test_platform_without_search_support_is_rejected(client):
    upsert_profile(client)
    response = create_search_session(client, platform="liepin")
    assert response.status_code == 409
    assert response.json()["detail"] == "当前平台暂不支持搜索能力。"
