import time
from datetime import datetime
from types import SimpleNamespace

from openresume_api.adapters.base import NormalizedJobDraft
from openresume_api.adapters.official import official_adapter
from openresume_api.automation.base import ApplyExecutionOutcome
from openresume_api.services.apply_batches import apply_batch_service


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
            "project_experiences": [],
            "awards": [],
            "source_filename": "resume.pdf" if with_resume else None,
            "source_language": "zh-CN",
            "raw_text": "React TypeScript resume",
        },
    )
    assert response.status_code == 200


def create_search_session(client, *, mode: str = "recommend_only"):
    return client.post(
        "/api/search-sessions",
        json={
            "platforms": ["official"],
            "mode": mode,
            "job_targets": ["Frontend Engineer"],
            "cities": ["Shanghai"],
            "salary_floor": 20000,
            "must_have_keywords": ["React"],
            "source_variants": [],
            "source_companies": [],
            "match_limit": 200,
            "company_job_limit": 200,
            "force_refresh": False,
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


def wait_for_batch_status(client, batch_id: str, expected: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = client.get(f"/api/apply-batches/{batch_id}")
        assert response.status_code == 200
        latest = response.json()
        if latest["status"] == expected:
            return latest
        time.sleep(0.15)
    raise AssertionError(f"batch {batch_id} did not reach status={expected}: {latest}")


def create_default_account(client, *, company_key: str = "bytedance"):
    response = client.post(
        "/api/official-accounts",
        json={
            "company_key": company_key,
            "display_name": "Primary Account",
            "username": "candidate@example.com",
            "password": "secret",
            "is_default": True,
            "status": "active",
        },
    )
    assert response.status_code == 200
    return response.json()


def upload_resume_asset(client, *, label: str = "Main Resume"):
    response = client.post(
        "/api/resume-assets",
        data={"label": label},
        files={"file": ("resume.pdf", b"%PDF-1.4 fake resume", "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()


def test_official_asset_endpoints_crud_and_binding_defaults(client):
    sites = client.get("/api/official-sites")
    assert sites.status_code == 200
    assert {item["company_key"] for item in sites.json()} == {
        "aliyun",
        "bytedance",
        "meituan",
        "pdd",
        "tencent",
    }

    first_account = create_default_account(client)
    second_account = client.post(
        "/api/official-accounts",
        json={
            "company_key": "bytedance",
            "display_name": "Backup Account",
            "username": "backup@example.com",
            "password": "secret-2",
            "is_default": True,
            "status": "active",
        },
    )
    assert second_account.status_code == 200

    accounts = client.get("/api/official-accounts", params={"company_key": "bytedance"})
    assert accounts.status_code == 200
    payload = accounts.json()
    assert len(payload) == 2
    assert sum(1 for item in payload if item["is_default"]) == 1
    assert payload[0]["session_cache"]["company_key"] == "bytedance"
    assert payload[0]["has_credentials"] is True

    resume_asset = upload_resume_asset(client)
    bindings = client.put(
        "/api/company-bindings/bytedance",
        json={"default_resume_asset_id": resume_asset["id"]},
    )
    assert bindings.status_code == 200
    assert bindings.json()["default_resume_asset_id"] == resume_asset["id"]

    listed_bindings = client.get("/api/company-bindings")
    assert listed_bindings.status_code == 200
    binding_index = {
        item["company_key"]: item["default_resume_asset_id"]
        for item in listed_bindings.json()
    }
    assert binding_index["bytedance"] == resume_asset["id"]

    deleted = client.delete(f"/api/resume-assets/{resume_asset['id']}")
    assert deleted.status_code == 204

    listed_bindings = client.get("/api/company-bindings")
    binding_index = {
        item["company_key"]: item["default_resume_asset_id"]
        for item in listed_bindings.json()
    }
    assert binding_index["bytedance"] is None

    removed = client.delete(f"/api/official-accounts/{first_account['id']}")
    assert removed.status_code == 204


def test_apply_batch_flow_uses_assets_and_supports_retry(client, monkeypatch):
    upsert_profile(client, with_resume=True)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    class FakeRuntime:
        def __init__(self):
            self.run_calls: list[dict[str, object]] = []
            self.capture_calls: list[dict[str, object]] = []
            self._outcomes = [
                ApplyExecutionOutcome(
                    status="needs_verification",
                    message="Verification required.",
                    verification_url="https://example.com/verify",
                    launch_url="https://example.com/verify",
                ),
                ApplyExecutionOutcome(
                    status="prepared",
                    message="Prepared and paused before final submit.",
                    launch_url="https://example.com/apply",
                ),
            ]

        async def run(self, *, storage_state_path: str, headless: bool, callback):
            self.run_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "headless": headless,
                }
            )
            return self._outcomes.pop(0)

        async def interactive_capture(
            self,
            *,
            storage_state_path: str,
            target_url: str,
            timeout_seconds: int = 300,
        ) -> None:
            self.capture_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "target_url": target_url,
                    "timeout_seconds": timeout_seconds,
                }
            )

    fake_runtime = FakeRuntime()
    monkeypatch.setattr(apply_batch_service, "_runtime", fake_runtime)
    monkeypatch.setattr(
        apply_batch_service,
        "_driver_getter",
        lambda company_key: SimpleNamespace(run=None, company_key=company_key),
    )

    session = create_search_session(client)
    assert session.status_code == 200
    session_id = session.json()["id"]
    wait_for_session_status(client, session_id, "ready")

    matches = client.get(f"/api/search-sessions/{session_id}/matches")
    assert matches.status_code == 200
    listing_id = matches.json()[0]["listing_id"]

    create_default_account(client)
    resume_asset = upload_resume_asset(client)
    binding = client.put(
        "/api/company-bindings/bytedance",
        json={"default_resume_asset_id": resume_asset["id"]},
    )
    assert binding.status_code == 200

    auto_submit_without_consent = client.post(
        "/api/apply-batches",
        json={
            "listing_ids": [listing_id],
            "execution_mode": "auto_submit",
            "session_id": session_id,
            "confirm_auto_submit": False,
        },
    )
    assert auto_submit_without_consent.status_code == 400

    created = client.post(
        "/api/apply-batches",
        json={
            "listing_ids": [listing_id],
            "execution_mode": "semi_auto",
            "session_id": session_id,
            "confirm_auto_submit": False,
        },
    )
    assert created.status_code == 200
    batch_id = created.json()["id"]

    blocked = wait_for_batch_status(client, batch_id, "needs_verification")
    assert blocked["items"][0]["status"] == "needs_verification"
    assert blocked["items"][0]["context"]["account_display_name"] == "Primary Account"
    assert blocked["items"][0]["context"]["resume_label"] == "Main Resume"

    filtered = client.get("/api/apply-batches", params={"session_id": session_id})
    assert filtered.status_code == 200
    assert filtered.json()[0]["id"] == batch_id

    resumed = client.post(f"/api/apply-batches/{batch_id}/continue")
    assert resumed.status_code == 200

    prepared = wait_for_batch_status(client, batch_id, "prepared")
    assert prepared["items"][0]["status"] == "prepared"
    assert prepared["items"][0]["message"] == "Prepared and paused before final submit."
    assert len(fake_runtime.run_calls) == 2
    assert fake_runtime.run_calls[0]["headless"] is False
    assert len(fake_runtime.capture_calls) == 1
