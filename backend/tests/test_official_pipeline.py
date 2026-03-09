import asyncio
import time

from sqlmodel import Session, select

import openresume_api.db as db_module
from openresume_api.adapters.base import NormalizedJobDraft, PlatformDataError
from openresume_api.adapters.official import SourceExtractionResult, official_adapter
from openresume_api.adapters.official_extractors.base import ExtractedCandidate
from openresume_api.models import CandidateProfile, JobListing
from openresume_api.schemas import SearchSessionCreate
from openresume_api.services.events import event_bus
from openresume_api.services.official_sources import OfficialSource, official_source_service


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
            "target_roles": ["Frontend Engineer", "Full Stack Engineer"],
            "preferred_cities": ["Shanghai", "Hangzhou"],
            "salary_floor": 25000,
            "years_experience": 5,
            "degree": "Bachelor",
            "skills": ["React", "TypeScript", "Node.js", "FastAPI"],
            "must_have_keywords": ["React", "TypeScript"],
            "source_language": "zh-CN",
        },
    )
    assert response.status_code == 200


def create_search_session(client):
    return client.post(
        "/api/search-sessions",
        json={
            "platforms": ["official"],
            "mode": "recommend_only",
            "job_targets": ["Frontend Engineer", "Full Stack Engineer"],
            "cities": ["Shanghai", "Hangzhou"],
            "salary_floor": 25000,
            "must_have_keywords": ["React", "TypeScript"],
        },
    )


def make_draft(external_job_id: str, quality_score: int) -> NormalizedJobDraft:
    tier = "high" if quality_score >= 80 else "medium" if quality_score >= 60 else "low"
    return NormalizedJobDraft(
        external_job_id=external_job_id,
        title="Senior Frontend Engineer",
        company_name="Example Corp",
        city="Shanghai",
        salary_text="30K-40K",
        salary_min=30000,
        salary_max=40000,
        experience_text="3-5 years",
        degree_text="Bachelor",
        work_mode="hybrid",
        url=f"https://example.com/jobs/{external_job_id}",
        detail_url=f"https://example.com/jobs/{external_job_id}",
        apply_url=f"https://example.com/jobs/{external_job_id}/apply",
        source_company_url="https://example.com/careers",
        apply_requires_login=True,
        jd_text="React TypeScript Node.js AI platform engineering",
        jd_hash=f"{external_job_id}-hash",
        raw_payload={
            "platform": "official",
            "quality": {
                "score": quality_score,
                "tier": tier,
                "drop_reasons": [],
                "penalty_reasons": [],
            },
            "detail_sections": {
                "responsibilities": "Build React hiring tools.",
                "requirements": "Strong TypeScript and testing experience.",
            },
            "department": "Platform",
            "location_text": "Shanghai",
        },
    )


def test_official_adapter_raises_when_cleaning_removes_all_jobs(monkeypatch):
    source = OfficialSource(
        company_name="Example Corp",
        url="https://careers.example.com",
        host="careers.example.com",
        source_kind="career_site",
    )
    candidate = ExtractedCandidate(
        title="FAQ",
        detail_url="https://careers.example.com/faq",
        apply_url="https://careers.example.com/faq",
        snippet="common questions",
        company_url="https://careers.example.com",
        city="Remote",
        salary_text="",
        salary_min=0,
        salary_max=0,
        experience_text="",
        degree_text="",
        work_mode="onsite",
        raw_payload={
            "seen_on": ["https://careers.example.com/faq"],
            "hard_filter_reasons": ["noise page"],
        },
    )

    async def fake_source_candidates(client, source, payload):
        return SourceExtractionResult(
            source=source,
            extractor="generic",
            entry_url=source.url,
            candidates=[candidate],
        )

    monkeypatch.setattr(official_source_service, "load_sources", lambda: (source,))
    monkeypatch.setattr(official_adapter, "_source_candidates", fake_source_candidates)

    payload = SearchSessionCreate(
        platforms=["official"],
        mode="recommend_only",
        job_targets=["Frontend Engineer"],
        cities=["Shanghai"],
        salary_floor=25000,
        must_have_keywords=["React"],
    )
    profile = CandidateProfile(
        id=1,
        target_roles=["Frontend Engineer"],
        preferred_cities=["Shanghai"],
        salary_floor=25000,
        skills=["React", "TypeScript"],
        must_have_keywords=["React"],
    )

    try:
        asyncio.run(official_adapter.search_jobs(payload, profile))
        raise AssertionError("expected PlatformDataError")
    except PlatformDataError as error:
        assert str(error) == "No official jobs passed code-based cleaning."

    assert official_adapter.last_run_stats == {
        "sources_selected": 1,
        "entry_candidates": 0,
        "hard_filtered": 1,
        "detail_dropped": 0,
        "quality_penalized": 0,
        "final_model_candidates": 0,
    }


def test_search_pipeline_fails_without_synthetic_fallback(client, monkeypatch):
    upsert_profile(client)

    async def fake_search_jobs(search, profile):
        raise PlatformDataError("No official jobs passed code-based cleaning.")

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client)
    assert session.status_code == 200

    failed = wait_for_session_status(client, session.json()["id"], "failed")
    assert "No official jobs passed code-based cleaning." in failed["summary"]

    matches = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches.status_code == 200
    assert matches.json() == []


def test_search_pipeline_filters_low_quality_penalizes_medium_and_persists_quality(client, monkeypatch):
    upsert_profile(client)
    stats = {
        "sources_selected": 3,
        "entry_candidates": 5,
        "hard_filtered": 1,
        "detail_dropped": 1,
        "quality_penalized": 1,
        "final_model_candidates": 2,
    }

    async def fake_search_jobs(search, profile):
        official_adapter.last_run_stats = stats
        return [
            make_draft("high-quality", 92),
            make_draft("medium-quality", 72),
            make_draft("low-quality", 55),
        ]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    session = create_search_session(client)
    assert session.status_code == 200

    wait_for_session_status(client, session.json()["id"], "ready")

    matches_response = client.get(f"/api/search-sessions/{session.json()['id']}/matches")
    assert matches_response.status_code == 200
    matches = matches_response.json()

    assert [item["external_job_id"] for item in matches] == [
        "high-quality",
        "medium-quality",
    ]
    medium_match = next(item for item in matches if item["external_job_id"] == "medium-quality")
    assert medium_match["rule_score"] == 68.0
    assert "\u5b98\u7f51\u4fe1\u606f\u8d28\u91cf\u4e00\u822c" in medium_match["risk_flags"]

    with Session(db_module.engine) as db:
        stored_jobs = db.exec(
            select(JobListing).where(JobListing.session_id == session.json()["id"])
        ).all()

    assert len(stored_jobs) == 2
    stored_by_external_id = {job.external_job_id: job for job in stored_jobs}
    assert "low-quality" not in stored_by_external_id
    assert stored_by_external_id["medium-quality"].raw_payload["quality"]["score"] == 72
    assert stored_by_external_id["medium-quality"].raw_payload["detail_sections"] == {
        "responsibilities": "Build React hiring tools.",
        "requirements": "Strong TypeScript and testing experience.",
    }

    code_cleaned_events = [
        event for event in event_bus.history(session.json()["id"]) if event["type"] == "code_cleaned"
    ]
    assert len(code_cleaned_events) == 1
    assert code_cleaned_events[0]["payload"] == stats
