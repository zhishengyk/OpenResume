import asyncio
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import openresume_api.main as main_module
from openresume_api.adapters.base import NormalizedJobDraft
from openresume_api.adapters.official import official_adapter
from openresume_api.automation.base import ApplyExecutionOutcome
from openresume_api.automation.official_drivers import get_official_driver
from openresume_api.career_collectors.manifest import load_sources
from openresume_api.services.apply_batches import apply_batch_service
from openresume_api.services.official_sites import get_official_site


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


def expected_official_company_keys() -> set[str]:
    return {source.collector_key for source in load_sources()}


def test_official_asset_endpoints_crud_and_binding_defaults(client):
    sites = client.get("/api/official-sites")
    assert sites.status_code == 200
    payload = sites.json()
    assert {item["company_key"] for item in payload} == expected_official_company_keys()
    assert len(payload) == len(expected_official_company_keys())
    assert all(item["login_url"] for item in payload)

    first_account = create_default_account(client)
    second_account_response = client.post(
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
    assert second_account_response.status_code == 200
    second_account = second_account_response.json()

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

    removed_default = client.delete(f"/api/official-accounts/{second_account['id']}")
    assert removed_default.status_code == 204

    accounts = client.get("/api/official-accounts", params={"company_key": "bytedance"})
    assert accounts.status_code == 200
    remaining_accounts = accounts.json()
    assert len(remaining_accounts) == 1
    assert remaining_accounts[0]["id"] == first_account["id"]
    assert remaining_accounts[0]["is_default"] is True

    removed = client.delete(f"/api/official-accounts/{first_account['id']}")
    assert removed.status_code == 204


def test_reverse_probed_login_launch_strategies_cover_all_sites():
    class FakePage:
        def __init__(self):
            self.gotos: list[str] = []
            self.click_selectors: list[list[str]] = []
            self.waits: list[int] = []
            self.scripts: list[str] = []
            self.url = ""

        async def goto(self, url: str) -> None:
            self.gotos.append(url)
            self.url = url

        async def current_url(self) -> str:
            return self.url

        async def wait_for_timeout(self, milliseconds: int) -> None:
            self.waits.append(milliseconds)

        async def try_click(self, selectors: list[str]) -> str | None:
            self.click_selectors.append(selectors)
            return selectors[0] if selectors else None

        async def evaluate(self, script: str) -> object:
            self.scripts.append(script)
            return True

        async def content_contains(self, markers: list[str]) -> bool:
            return False

        async def has_any(self, selectors: list[str]) -> str | None:
            return None

        async def try_set_input_files(self, selectors: list[str], file_path: str) -> str | None:
            return None

        async def try_fill(self, selectors: list[str], value: str) -> str | None:
            return None

    expectations = {
        "bytedance": {
            "url": "https://jobs.bytedance.com/experienced/login",
            "clicks": 0,
            "scripts": 0,
        },
        "tencent": {
            "url": "https://careers.tencent.com/login.html?state=https%3A%2F%2Fcareers.tencent.com%2F",
            "clicks": 0,
            "scripts": 0,
        },
        "tme": {
            "url": "https://join.tencentmusic.com/login",
            "clicks": 0,
            "scripts": 0,
        },
        "baidu": {
            "url": "https://talent.baidu.com/",
            "clicks": 0,
            "scripts": 0,
        },
        "didi": {
            "url": "https://talent.didiglobal.com/social/list/1",
            "clicks": 0,
            "scripts": 0,
        },
        "ctrip": {
            "url": "https://job.ctrip.com/",
            "clicks": 0,
            "scripts": 0,
        },
        "netease": {
            "url": "https://hr.163.com/",
            "clicks": 0,
            "scripts": 0,
        },
        "quark": {
            "url": "https://talent.quark.cn/off-campus/home?lang=zh",
            "clicks": 0,
            "scripts": 1,
        },
        "taobao": {
            "url": "https://talent.taotian.com/",
            "clicks": 0,
            "scripts": 1,
        },
        "aliyun": {
            "url": "https://careers.aliyun.com/off-campus/home?lang=zh",
            "clicks": 0,
            "scripts": 1,
        },
        "alibaba_holding": {
            "url": "https://talent-holding.alibaba.com/",
            "clicks": 0,
            "scripts": 1,
        },
        "meituan": {
            "url": "https://zhaopin.meituan.com/web/login?redirectUrl=https%3A%2F%2Fzhaopin.meituan.com%2Fweb%2Fhome",
            "clicks": 0,
            "scripts": 0,
        },
        "pdd": {
            "url": "https://careers.pddglobalhr.com/campus/",
            "clicks": 1,
            "scripts": 0,
        },
        "kuaishou": {
            "url": "https://zhaopin.kuaishou.cn/#/official/login/",
            "clicks": 0,
            "scripts": 0,
        },
        "jd": {
            "url": "https://passport.jd.com/new/login.aspx?ReturnUrl=https%3A%2F%2Fzhaopin.jd.com%2Ferror",
            "clicks": 0,
            "scripts": 0,
        },
        "ant": {
            "url": "https://talent.antgroup.com/login",
            "clicks": 0,
            "scripts": 0,
        },
        "amap": {
            "url": "https://talent.amap.com/off-campus/position-list?lang=zh",
            "clicks": 0,
            "scripts": 1,
        },
        "eleme": {
            "url": "https://talent.ele.me/off-campus/position-list?lang=zh",
            "clicks": 0,
            "scripts": 1,
        },
        "aidc": {
            "url": "https://aidc-jobs.alibaba.com/off-campus/position-list?lang=zh",
            "clicks": 0,
            "scripts": 1,
        },
        "xiaohongshu": {
            "url": "https://job.xiaohongshu.com/login",
            "clicks": 0,
            "scripts": 0,
        },
        "bilibili": {
            "url": "https://jobs.bilibili.com/",
            "clicks": 1,
            "scripts": 0,
        },
        "dewu": {
            "url": "https://poizon.jobs.feishu.cn/index",
            "clicks": 1,
            "scripts": 0,
        },
        "freshippo": {
            "url": "https://hire.freshippo.com/?lang=zh",
            "clicks": 0,
            "scripts": 1,
        },
        "mihoyo": {
            "url": "https://jobs.mihoyo.com/recommendation/login",
            "clicks": 0,
            "scripts": 0,
        },
    }

    assert set(expectations) == expected_official_company_keys()

    for company_key, expectation in expectations.items():
        page = FakePage()
        driver = get_official_driver(company_key)
        site = get_official_site(company_key)
        asyncio.run(driver.launch_login(page, target_url=site.login_url))
        assert page.gotos == [expectation["url"]]
        assert len(page.click_selectors) == expectation["clicks"]
        assert len(page.scripts) == expectation["scripts"]
        assert page.waits


def test_check_session_accepts_redirect_away_from_login_page():
    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url: str) -> None:
            self.url = "https://jobs.bytedance.com/experienced/"

        async def current_url(self) -> str:
            return self.url

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        async def try_click(self, selectors: list[str]) -> str | None:
            return None

        async def evaluate(self, script: str) -> object:
            return None

        async def content_contains(self, markers: list[str]) -> bool:
            return True

        async def has_any(self, selectors: list[str]) -> str | None:
            return None

        async def try_set_input_files(self, selectors: list[str], file_path: str) -> str | None:
            return None

        async def try_fill(self, selectors: list[str], value: str) -> str | None:
            return None

    driver = get_official_driver("bytedance")
    ready, message = asyncio.run(
        driver.check_session(
            FakePage(),
            target_url="https://jobs.bytedance.com/experienced/login",
        )
    )

    assert ready is True
    assert "登录缓存可用" in message


def test_tencent_check_session_accepts_homepage_ready_markers():
    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url: str) -> None:
            self.url = "https://careers.tencent.com/"

        async def current_url(self) -> str:
            return self.url

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        async def try_click(self, selectors: list[str]) -> str | None:
            return None

        async def evaluate(self, script: str) -> object:
            return None

        async def content_contains(self, markers: list[str]) -> bool:
            marker_set = {marker.casefold() for marker in markers}
            if "\u6295\u9012\u8bb0\u5f55".casefold() in marker_set:
                return True
            if "\u767b\u5f55".casefold() in marker_set:
                return True
            return False

        async def has_any(self, selectors: list[str]) -> str | None:
            return None

        async def try_set_input_files(self, selectors: list[str], file_path: str) -> str | None:
            return None

        async def try_fill(self, selectors: list[str], value: str) -> str | None:
            return None

    driver = get_official_driver("tencent")
    site = get_official_site("tencent")
    ready, message = asyncio.run(
        driver.check_session(
            FakePage(),
            target_url=site.session_check_url or site.login_url,
        )
    )

    assert ready is True
    assert site.session_check_url == "https://careers.tencent.com/"
    assert "\u767b\u5f55\u7f13\u5b58\u53ef\u7528" in message


def test_official_account_login_and_session_test_update_binary_status(client, monkeypatch):
    class FakeRuntime:
        def __init__(self):
            self.interactive_calls: list[dict[str, object]] = []
            self.inspect_responses = [
                (True, "字节跳动登录缓存可用。"),
                (False, "字节跳动当前未登录，请先在账号池完成登录。"),
            ]

        async def inspect(self, *, storage_state_path: str, headless: bool, callback):
            return self.inspect_responses.pop(0)

        async def interactive_run(
            self,
            *,
            storage_state_path: str,
            callback,
            completion_callback=None,
            completion_poll_ms: int = 1000,
            timeout_seconds: int = 300,
        ) -> None:
            path = Path(storage_state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            self.interactive_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "timeout_seconds": timeout_seconds,
                }
            )

    fake_runtime = FakeRuntime()
    monkeypatch.setattr(main_module, "playwright_automation_runtime", fake_runtime)

    account = create_default_account(client)

    login_response = client.post(f"/api/official-accounts/{account['id']}/login")
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["is_logged_in"] is True
    assert login_payload["last_test_message"] == "字节跳动登录缓存可用。"
    assert login_payload["session_cache"]["status"] == "ready"
    assert len(fake_runtime.interactive_calls) == 1

    session_test = client.post(f"/api/official-accounts/{account['id']}/session-test")
    assert session_test.status_code == 200
    session_payload = session_test.json()
    assert session_payload["is_logged_in"] is False
    assert "未登录" in session_payload["last_test_message"]
    assert session_payload["session_cache"]["status"] == "missing"


def test_apply_batch_fails_fast_without_login_cache(client, monkeypatch):
    upsert_profile(client, with_resume=True)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    class FakeRuntime:
        def __init__(self):
            self.inspect_calls: list[dict[str, object]] = []
            self.run_calls: list[dict[str, object]] = []

        async def inspect(self, *, storage_state_path: str, headless: bool, callback):
            self.inspect_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "headless": headless,
                }
            )
            return True, "ready"

        async def run(self, *, storage_state_path: str, headless: bool, callback):
            self.run_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "headless": headless,
                }
            )
            return ApplyExecutionOutcome(status="submitted", message="should not run")

    fake_runtime = FakeRuntime()
    monkeypatch.setattr(apply_batch_service, "_runtime", fake_runtime)
    monkeypatch.setattr(
        apply_batch_service,
        "_driver_getter",
        lambda company_key: SimpleNamespace(run=None, check_session=None, company_key=company_key),
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

    failed = wait_for_batch_status(client, batch_id, "failed")
    assert failed["items"][0]["status"] == "failed"
    assert "先在账号池完成官网登录" in failed["items"][0]["message"]
    assert fake_runtime.inspect_calls == []
    assert fake_runtime.run_calls == []


def test_apply_batch_flow_uses_assets_and_supports_retry(client, monkeypatch):
    upsert_profile(client, with_resume=True)

    async def fake_search_jobs(search, profile):
        return [sample_draft()]

    monkeypatch.setattr(official_adapter, "search_jobs", fake_search_jobs)

    class FakeRuntime:
        def __init__(self):
            self.run_calls: list[dict[str, object]] = []
            self.capture_calls: list[dict[str, object]] = []
            self.inspect_calls: list[dict[str, object]] = []
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

        async def inspect(self, *, storage_state_path: str, headless: bool, callback):
            self.inspect_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "headless": headless,
                }
            )
            return True, "ByteDance session is ready."

        async def run(self, *, storage_state_path: str, headless: bool, callback):
            self.run_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "headless": headless,
                }
            )
            return self._outcomes.pop(0)

        async def interactive_run(
            self,
            *,
            storage_state_path: str,
            callback,
            completion_callback=None,
            completion_poll_ms: int = 1000,
            timeout_seconds: int = 300,
        ) -> None:
            path = Path(storage_state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            self.capture_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "timeout_seconds": timeout_seconds,
                    "kind": "login",
                }
            )

        async def interactive_capture(
            self,
            *,
            storage_state_path: str,
            target_url: str,
            timeout_seconds: int = 300,
        ) -> None:
            path = Path(storage_state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            self.capture_calls.append(
                {
                    "storage_state_path": storage_state_path,
                    "target_url": target_url,
                    "timeout_seconds": timeout_seconds,
                    "kind": "verify",
                }
            )

    fake_runtime = FakeRuntime()
    monkeypatch.setattr(apply_batch_service, "_runtime", fake_runtime)
    monkeypatch.setattr(main_module, "playwright_automation_runtime", fake_runtime)
    monkeypatch.setattr(
        apply_batch_service,
        "_driver_getter",
        lambda company_key: SimpleNamespace(
            run=None,
            check_session=None,
            company_key=company_key,
        ),
    )

    session = create_search_session(client)
    assert session.status_code == 200
    session_id = session.json()["id"]
    wait_for_session_status(client, session_id, "ready")

    matches = client.get(f"/api/search-sessions/{session_id}/matches")
    assert matches.status_code == 200
    listing_id = matches.json()[0]["listing_id"]

    account = create_default_account(client)
    resume_asset = upload_resume_asset(client)
    binding = client.put(
        "/api/company-bindings/bytedance",
        json={"default_resume_asset_id": resume_asset["id"]},
    )
    assert binding.status_code == 200

    login = client.post(f"/api/official-accounts/{account['id']}/login")
    assert login.status_code == 200
    assert login.json()["is_logged_in"] is True

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
    assert len(fake_runtime.inspect_calls) == 3
    assert fake_runtime.run_calls[0]["headless"] is False
    assert len(fake_runtime.capture_calls) == 2
    assert fake_runtime.capture_calls[0]["kind"] == "login"
    assert fake_runtime.capture_calls[1]["target_url"] == "https://example.com/verify"

    accounts = client.get("/api/official-accounts", params={"company_key": "bytedance"})
    assert accounts.status_code == 200
    assert accounts.json()[0]["last_test_message"] == "Prepared and paused before final submit."
