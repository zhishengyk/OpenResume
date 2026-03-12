import asyncio
from datetime import datetime

import httpx
from openresume_api.adapters.base import NormalizedJobDraft
from openresume_api.adapters.official import official_adapter
from openresume_api.models import CandidateProfile, JobListing
from openresume_api.services.llm import OpenAICompatibleLLMProvider
from openresume_api.services.llm_common import extract_chat_message_text
from openresume_api.services.runtime_config import LLMRuntimeConfig


def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        id=1,
        full_name="Test Candidate",
        headline="Senior Frontend Engineer",
        summary="React TypeScript engineer",
        target_roles=["Frontend Engineer"],
        preferred_cities=["Shanghai"],
        salary_floor=25000,
        years_experience=5,
        degree="Bachelor",
        skills=["React", "TypeScript"],
        must_have_keywords=["React"],
        tech_stack=["React", "TypeScript"],
        project_experiences=[],
        awards=[],
        source_language="zh-CN",
        raw_text="React TypeScript",
    )


def sample_job() -> JobListing:
    return JobListing(
        session_id="session-1",
        platform="official",
        source_company="ByteDance",
        source_site="jobs.bytedance.com",
        job_id="job-1",
        title="Frontend Engineer",
        description_text="Need React and TypeScript",
        requirements_text="Strong React",
        salary_min=30000,
        salary_max=40000,
        crawl_time=datetime(2026, 3, 10),
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
        description_html="<p>React TypeScript official site flow</p>",
        description_text="React TypeScript official site flow",
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


def wait_for_session_status(client, session_id: str, expected: str, timeout: float = 5.0):
    import time

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
    import time

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


def upsert_profile(client):
    response = client.put(
        "/api/profile",
        json={
            "id": 1,
            "full_name": "Test Candidate",
            "headline": "Senior Frontend Engineer",
            "summary": "React and TypeScript engineer",
            "target_roles": ["Frontend Engineer"],
            "preferred_cities": ["Shanghai"],
            "salary_floor": 25000,
            "years_experience": 5,
            "degree": "Bachelor",
            "skills": ["React", "TypeScript"],
            "must_have_keywords": ["React", "TypeScript"],
            "tech_stack": ["React", "TypeScript"],
            "project_experiences": [],
            "awards": [],
            "source_filename": None,
            "source_language": "zh-CN",
            "raw_text": "React TypeScript resume",
        },
    )
    assert response.status_code == 200


def create_search_session(client):
    return client.post(
        "/api/search-sessions",
        json={
            "platforms": ["official"],
            "mode": "recommend_only",
            "job_targets": ["Frontend Engineer"],
            "cities": ["Shanghai"],
            "salary_floor": 0,
            "must_have_keywords": [],
            "source_variants": [],
            "source_companies": [],
            "match_limit": 20,
            "company_job_limit": 20,
            "force_refresh": False,
        },
    )


def test_extract_chat_message_text_supports_reasoning_and_tool_calls():
    assert extract_chat_message_text({"content": "OK"}) == "OK"
    assert (
        extract_chat_message_text({"content": None, "reasoning_content": "JSON here"})
        == "JSON here"
    )
    assert (
        extract_chat_message_text(
            {
                "content": [{"type": "text", "text": "hello"}],
                "reasoning_content": "fallback",
            }
        )
        == "hello"
    )
    assert (
        extract_chat_message_text(
            {
                "tool_calls": [
                    {"function": {"arguments": '{"results": []}'}},
                ]
            }
        )
        == '{"results": []}'
    )


def test_openai_provider_can_parse_json_from_reasoning_content(monkeypatch):
    provider = OpenAICompatibleLLMProvider(
        LLMRuntimeConfig(
            llm_provider="openai_compatible",
            openai_base_url="https://example.com/v1",
            openai_api_key="secret",
            openai_model="test-model",
        )
    )

    payload = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "reasoning_content": (
                        '{"results": [{"job_id": "job-1", "llm_score": 92, '
                        '"highlights": ["React"], "missing_keywords": [], '
                        '"risk_flags": [], "llm_summary": "Strong match"}]}'
                    ),
                }
            }
        ]
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
            assert url == "https://example.com/v1/chat/completions"
            assert json["model"] == "test-model"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    results = asyncio.run(provider.analyze(sample_profile(), [sample_job()]))

    assert len(results) == 1
    assert results[0].job_id == "job-1"
    assert results[0].llm_score == 92.0
    assert results[0].llm_summary == "Strong match"
    assert results[0].highlights == ["React"]


def test_incomplete_openai_config_falls_back_to_heuristic_in_search_pipeline(
    client, monkeypatch
):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

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
    assert update.json()["llm_configured"] is False

    session = create_search_session(client)
    assert session.status_code == 200
    session_id = session.json()["id"]

    wait_for_session_status(client, session_id, "ready")
    enriched = wait_for_analysis_status(client, session_id, "ready")
    assert enriched["analysis_provider"] == "heuristic"
    assert enriched["analysis_degraded"] is True
    assert "缺少必要配置" in (enriched["analysis_notice"] or "")

    matches = client.get(f"/api/search-sessions/{session_id}/matches")
    assert matches.status_code == 200
    payload = matches.json()
    assert len(payload) == 1
    assert payload[0]["analysis_provider"] == "heuristic"
    assert payload[0]["analysis_degraded"] is True
    assert payload[0]["llm_score"] is not None
