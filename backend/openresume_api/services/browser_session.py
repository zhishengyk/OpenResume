from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
import os
from pathlib import Path
import socket
import subprocess
import time
from typing import Any
import webbrowser

from sqlmodel import Session

from ..config import settings
from ..models import AppSetting

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright
except Exception:  # pragma: no cover - optional dependency guard
    BrowserContext = Any  # type: ignore[assignment]
    Page = Any  # type: ignore[assignment]
    PlaywrightTimeoutError = Exception  # type: ignore[assignment]
    async_playwright = None


@dataclass
class BrowserRuntime:
    context: BrowserContext
    page: Page
    engine: str
    work_page: Page | None = None
    browser: Any | None = None
    managed_context: bool = True


class BrowserSessionService:
    EXTERNAL_DEBUG_PORTS = {
        "boss": 39221,
    }

    def __init__(self) -> None:
        self._playwright = None
        self._runtimes: dict[str, BrowserRuntime] = {}
        self._lock = asyncio.Lock()

    def session_dir(self, platform: str) -> Path:
        directory = settings.browser_dir / platform
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _has_persisted_profile(self, platform: str) -> bool:
        storage_dir = self.session_dir(platform)
        required_files = [
            storage_dir / "Local State",
            storage_dir / "Default" / "Preferences",
            storage_dir / "Default" / "Network" / "Cookies",
        ]
        for path in required_files:
            try:
                if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
                    return False
            except Exception:
                return False
        return True

    def _upsert_state(self, db: Session, platform: str, values: dict) -> dict:
        key = f"platform_session:{platform}"
        setting = db.get(AppSetting, key)
        if not setting:
            setting = AppSetting(key=key, value={})
        setting.value = {
            **(setting.value or {}),
            **values,
        }
        setting.updated_at = datetime.utcnow()
        db.add(setting)
        db.commit()
        return setting.value

    def set_search_ready(
        self,
        db: Session,
        platform: str,
        ready: bool,
        *,
        reason: str | None = None,
    ) -> dict:
        payload = {
            "search_ready": ready,
            "search_ready_checked_at": datetime.utcnow().isoformat(),
        }
        if reason:
            payload["search_ready_reason"] = reason
        return self._upsert_state(db, platform, payload)

    async def _ensure_playwright(self):
        if async_playwright is None:
            raise RuntimeError(
                "Playwright \u672a\u5b89\u88c5\uff0c\u8bf7\u5148\u6267\u884c "
                "`python -m pip install -e .[automation]` \u548c "
                "`python -m playwright install chromium`\u3002"
            )

        if self._playwright is None:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def _ensure_runtime(self, platform: str) -> BrowserRuntime:
        existing = self._runtimes.get(platform)
        if existing and not existing.page.is_closed():
            return existing

        async with self._lock:
            existing = self._runtimes.get(platform)
            if existing and not existing.page.is_closed():
                return existing

            playwright = await self._ensure_playwright()
            external_runtime = await self._connect_external_runtime(playwright, platform)
            if external_runtime is not None:
                self._runtimes[platform] = external_runtime
                return external_runtime
            context, engine = await self._launch_context(playwright, platform)
            page = context.pages[0] if context.pages else await context.new_page()
            runtime = BrowserRuntime(context=context, page=page, engine=engine)
            self._runtimes[platform] = runtime
            return runtime

    async def _launch_context(self, playwright, platform: str) -> tuple[BrowserContext, str]:
        # Hide Playwright automation fingerprints to avoid anti-bot detection.
        stealth_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-extensions-except=",
        ]
        launch_options = {
            "user_data_dir": str(self.session_dir(platform)),
            "headless": settings.disable_browser_open,
            "viewport": {"width": 1440, "height": 960},
            "args": stealth_args,
            # Mask navigator.webdriver and related automation properties.
            "ignore_default_args": ["--enable-automation"],
        }
        errors: list[str] = []

        try:
            context = await playwright.chromium.launch_persistent_context(
                **launch_options,
                channel="msedge",
            )
            # Override navigator.webdriver at the page level so Boss JS cannot detect it.
            await context.add_init_script("""
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
window.chrome = { runtime: {} };
""")
            return context, "msedge"
        except Exception as error:
            errors.append(f"msedge: {error}")

        joined = " | ".join(errors)
        raise RuntimeError(
            "Playwright 无法启动 Microsoft Edge。"
            " 请确认系统已安装 Edge，且 Boss 专用会话没有被其他浏览器进程占用。"
            f" 当前错误：{joined}"
        )

    async def _ensure_page(self, platform: str) -> Page:
        runtime = await self._ensure_runtime(platform)
        if runtime.page.is_closed():
            runtime.page = (
                runtime.context.pages[0]
                if runtime.context.pages
                else await runtime.context.new_page()
            )
        await self._stabilize_runtime_page(runtime)
        return runtime.page

    def _has_runtime(self, platform: str) -> bool:
        runtime = self._runtimes.get(platform)
        return bool(runtime and not runtime.page.is_closed())

    @staticmethod
    def _edge_binary_path() -> Path | None:
        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", ""))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
            Path(os.environ.get("ProgramFiles", ""))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @classmethod
    def _external_debug_port(cls, platform: str) -> int | None:
        return cls.EXTERNAL_DEBUG_PORTS.get(platform)

    @staticmethod
    def _powershell_executable() -> str:
        return "powershell.exe"

    @staticmethod
    def _is_internal_page(url: str) -> bool:
        lowered = url.lower()
        return lowered.startswith("edge://") or lowered.startswith("chrome://") or lowered.startswith("devtools://")

    @staticmethod
    def _is_login_page(url: str) -> bool:
        lowered = url.lower()
        return "/web/user" in lowered or "passport-zp" in lowered

    @staticmethod
    def _is_search_page(url: str) -> bool:
        lowered = url.lower()
        return "/web/geek/job" in lowered or "/web/geek/jobs" in lowered

    def _preferred_runtime_page(self, context: BrowserContext) -> Page | None:
        pages = list(context.pages)
        if not pages:
            return None

        for page in reversed(pages):
            url = page.url or ""
            if self._is_login_page(url):
                return page

        for page in reversed(pages):
            url = page.url or ""
            if url and not url.startswith("about:blank") and not self._is_internal_page(url):
                return page

        for page in reversed(pages):
            url = page.url or ""
            if url and not self._is_internal_page(url):
                return page

        if context.pages:
            return context.pages[-1]
        return None

    def _preferred_work_page(self, runtime: BrowserRuntime) -> Page | None:
        pages = list(runtime.context.pages)
        if not pages:
            return None

        for page in reversed(pages):
            if page.is_closed() or page is runtime.page:
                continue
            url = page.url or ""
            if self._is_search_page(url):
                return page

        for page in reversed(pages):
            if page.is_closed() or page is runtime.page:
                continue
            url = page.url or ""
            if url and not url.startswith("about:blank") and not self._is_internal_page(url):
                return page

        return None

    async def _stabilize_runtime_page(self, runtime: BrowserRuntime) -> Page:
        # Wait up to 5 s for at least one non-blank page to appear.
        # Boss JS often opens a new tab and leaves the original page on
        # about:blank; we need to give it time to do so.
        deadline = asyncio.get_event_loop().time() + 5.0
        while asyncio.get_event_loop().time() < deadline:
            pages = [p for p in runtime.context.pages if not p.is_closed()]
            if any(
                (p.url or "") and not (p.url or "").startswith("about:blank")
                for p in pages
            ):
                break
            await asyncio.sleep(0.3)

        for page in list(runtime.context.pages):
            if page is runtime.page or page.is_closed():
                continue
            try:
                if (page.url or "").startswith("about:blank") and len(runtime.context.pages) > 1:
                    await page.close()
            except Exception:
                pass

        preferred = self._preferred_runtime_page(runtime.context)
        if preferred is not None and not preferred.is_closed():
            runtime.page = preferred

        preferred_work_page = self._preferred_work_page(runtime)
        if preferred_work_page is not None and not preferred_work_page.is_closed():
            runtime.work_page = preferred_work_page
        elif runtime.work_page is runtime.page:
            runtime.work_page = None

        if not settings.disable_browser_open and not runtime.page.is_closed():
            try:
                await runtime.page.bring_to_front()
            except Exception:
                pass

        return runtime.page

    async def _ensure_work_page(self, runtime: BrowserRuntime) -> Page:
        await self._stabilize_runtime_page(runtime)

        page = runtime.work_page
        if (
            page is not None
            and not page.is_closed()
            and page is not runtime.page
        ):
            return page

        preferred = self._preferred_work_page(runtime)
        if preferred is not None and not preferred.is_closed():
            runtime.work_page = preferred
            return preferred

        page = await runtime.context.new_page()
        runtime.work_page = page
        return page

    async def _connect_external_runtime(self, playwright, platform: str) -> BrowserRuntime | None:
        if settings.disable_browser_open:
            return None
        port = self._external_debug_port(platform)
        if port is None:
            return None

        try:
            browser = await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}",
                timeout=2500,
            )
        except Exception:
            return None

        if not browser.contexts:
            logger.warning(
                "external browser CDP connected but no contexts found: platform=%s port=%s",
                platform,
                port,
            )
            return None

        context = browser.contexts[0]
        page = self._preferred_runtime_page(context)
        if page is None or page.is_closed():
            try:
                page = await context.new_page()
            except Exception as error:
                logger.warning(
                    "external browser CDP connected but could not create page: platform=%s port=%s error=%s",
                    platform,
                    port,
                    error,
                )
                return None

        return BrowserRuntime(
            context=context,
            page=page,
            engine="external_edge_cdp",
            browser=browser,
            managed_context=False,
        )

    def _list_profile_browser_processes(self, platform: str) -> list[dict[str, Any]]:
        if os.name != "nt":
            return []

        session_dir = str(self.session_dir(platform)).replace("'", "''")
        script = f"""
$target = '{session_dir}'
$items = Get-CimInstance Win32_Process | Where-Object {{
  ($_.Name -in @('chrome.exe', 'msedge.exe')) -and $_.CommandLine -like "*$target*"
}} | Select-Object ProcessId, Name, CommandLine
if ($items) {{
  $items | ConvertTo-Json -Compress
}}
"""
        result = subprocess.run(
            [self._powershell_executable(), "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or "").strip()
        if result.returncode != 0 or not output:
            return []

        try:
            import json

            payload = json.loads(output)
        except Exception:
            logger.warning(
                "failed to parse profile browser process list: platform=%s output=%s",
                platform,
                output,
            )
            return []

        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return payload
        return []

    def _cleanup_profile_browser_processes(self, platform: str) -> None:
        if os.name != "nt":
            return

        processes = self._list_profile_browser_processes(platform)
        if not processes:
            return

        for process in processes:
            pid = process.get("ProcessId")
            if not pid:
                continue
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except Exception as error:
                logger.warning(
                    "failed to terminate session browser process: platform=%s pid=%s error=%s",
                    platform,
                    pid,
                    error,
                )

        deadline = time.time() + 5
        while time.time() < deadline:
            if not self._list_profile_browser_processes(platform):
                break
            time.sleep(0.25)

    def _wait_for_external_debug_port(
        self,
        platform: str,
        timeout_seconds: float = 8.0,
    ) -> bool:
        port = self._external_debug_port(platform)
        if port is None:
            return False

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.4)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    return True
            time.sleep(0.25)
        return False

    async def _ensure_external_runtime(self, platform: str) -> BrowserRuntime:
        existing = self._runtimes.get(platform)
        if (
            existing
            and existing.engine == "external_edge_cdp"
            and not existing.page.is_closed()
        ):
            return existing

        async with self._lock:
            existing = self._runtimes.get(platform)
            if (
                existing
                and existing.engine == "external_edge_cdp"
                and not existing.page.is_closed()
            ):
                return existing
            playwright = await self._ensure_playwright()
            runtime = await self._connect_external_runtime(playwright, platform)
            if runtime is None:
                raise RuntimeError(
                    "Boss 专用会话浏览器未就绪，请先点击“启动 / 重新打开 Boss 会话”，"
                    "并保持该专用 Edge 窗口处于打开状态。"
                )
            self._runtimes[platform] = runtime
            return runtime

    def _should_use_external_session_browser(self, platform: str, reason: str) -> bool:
        # Boss aggressively detects Playwright automation (closes page on DevTools,
        # detects navigator.webdriver, etc.). Always use a real external Edge window
        # for the session so the user can log in without triggering anti-bot checks.
        return platform == "boss"

    def _open_external_session_browser(self, platform: str, url: str) -> str:
        edge_path = self._edge_binary_path()
        storage_dir = self.session_dir(platform)
        debug_port = self._external_debug_port(platform)
        if edge_path is not None:
            command = [
                str(edge_path),
                f"--user-data-dir={storage_dir}",
                "--no-first-run",
                "--new-window",
            ]
            if debug_port is not None:
                command.append(f"--remote-debugging-port={debug_port}")
            command.append(url)
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            return "external_edge"
        webbrowser.open(url)
        return "external"

    async def _reset_runtime(self, platform: str) -> None:
        runtime = self._runtimes.pop(platform, None)
        if not runtime:
            return
        if runtime.managed_context:
            try:
                await runtime.context.close()
            except Exception:
                pass

    async def _navigate(
        self,
        platform: str,
        url: str,
        *,
        force_new_page: bool = False,
        wait_until: str = "commit",
        timeout: int = 15000,
    ) -> str:
        runtime = await self._ensure_runtime(platform)
        if force_new_page or runtime.page.is_closed():
            runtime.page = await runtime.context.new_page()
        page = runtime.page
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
        except Exception as nav_error:
            logger.warning(
                "page.goto error: platform=%s url=%s error=%s page_url=%s",
                platform, url, nav_error, page.url,
            )

        # Boss sometimes opens a new tab for the real content and leaves the
        # original tab on about:blank. Wait briefly, then let _stabilize_runtime_page
        # pick the best available page. Do NOT re-navigate here — that would
        # interfere with Boss's own redirect chain and cause a refresh loop.
        await asyncio.sleep(2.0)
        page = await self._stabilize_runtime_page(runtime)
        current_url = page.url or ""
        if not current_url or current_url.startswith("about:blank"):
            raise RuntimeError(f"session navigate failed, stayed on about:blank for {url}")
        return current_url

    async def start(self, db: Session, platform: str, login_url: str) -> dict:
        storage_dir = self.session_dir(platform)
        setting = db.get(AppSetting, f"platform_session:{platform}")
        if settings.disable_browser_open:
            return self._upsert_state(
                db,
                platform,
                {
                    "active": True,
                    "last_started_at": datetime.utcnow().isoformat(),
                    "storage_dir": str(storage_dir),
                    "runtime": "disabled",
                },
            )

        if setting and self._has_runtime(platform):
            last_started_at = setting.value.get("last_started_at")
            try:
                if last_started_at:
                    elapsed = datetime.utcnow() - datetime.fromisoformat(last_started_at)
                    if elapsed.total_seconds() < 10:
                        page = await self._ensure_page(platform)
                        return self._upsert_state(
                            db,
                            platform,
                            {
                                "active": True,
                                "storage_dir": str(storage_dir),
                                "last_opened_url": page.url or login_url,
                                "last_opened_reason": "session_start_reuse",
                                "last_opened_at": datetime.utcnow().isoformat(),
                            },
                        )
            except Exception:
                pass

        if platform == "boss":
            await self._reset_runtime(platform)
            self._cleanup_profile_browser_processes(platform)

        if self._should_use_external_session_browser(platform, "session_start"):
            await self._reset_runtime(platform)
            self._cleanup_profile_browser_processes(platform)
            runtime = self._open_external_session_browser(platform, login_url)
            if not self._wait_for_external_debug_port(platform):
                raise RuntimeError(
                    "Boss 专用会话浏览器启动失败：未检测到调试端口。"
                    " 请先关闭残留的 Boss 专用浏览器窗口后再重试。"
                )
            return self._upsert_state(
                db,
                platform,
                {
                    "active": True,
                    "search_ready": False,
                    "last_started_at": datetime.utcnow().isoformat(),
                    "storage_dir": str(storage_dir),
                    "last_opened_url": login_url,
                    "last_opened_reason": "session_start",
                    "last_opened_at": datetime.utcnow().isoformat(),
                    "runtime": runtime,
                },
            )

        try:
            current_url = await self._navigate(
                platform,
                login_url,
                force_new_page=True,
                timeout=30000,
            )
            runtime = "playwright"
        except Exception as nav_error:
            logger.warning(
                "session start navigate failed, falling back to external browser: platform=%s url=%s error=%s",
                platform,
                login_url,
                nav_error,
            )
            await self._reset_runtime(platform)
            self._cleanup_profile_browser_processes(platform)
            self._open_external_session_browser(platform, login_url)
            current_url = login_url
            runtime = "external_edge"

        return self._upsert_state(
            db,
            platform,
            {
                "active": True,
                "search_ready": False,
                "last_started_at": datetime.utcnow().isoformat(),
                "storage_dir": str(storage_dir),
                "last_opened_url": current_url,
                "last_opened_reason": "session_start",
                "last_opened_at": datetime.utcnow().isoformat(),
                "runtime": runtime,
            },
        )

    async def open_runtime_url(self, platform: str, url: str) -> str:
        if settings.disable_browser_open:
            return url
        return await self._navigate(platform, url)

    async def open_url(self, db: Session, platform: str, url: str, reason: str) -> dict:
        storage_dir = self.session_dir(platform)
        setting = db.get(AppSetting, f"platform_session:{platform}")
        last_opened_url = setting.value.get("last_opened_url") if setting else None
        last_opened_reason = setting.value.get("last_opened_reason") if setting else None
        last_opened_at = setting.value.get("last_opened_at") if setting else None
        # Debounce repeated open request to prevent visible page loops.
        if (
            last_opened_url == url
            and last_opened_reason == reason
            and isinstance(last_opened_at, str)
        ):
            try:
                elapsed = datetime.utcnow() - datetime.fromisoformat(last_opened_at)
                if elapsed.total_seconds() < 8:
                    return self._upsert_state(
                        db,
                        platform,
                        {
                            "active": True,
                            "storage_dir": str(storage_dir),
                        },
                    )
            except Exception:
                pass

        if settings.disable_browser_open:
            current_url = url
            runtime = "disabled"
        elif self._should_use_external_session_browser(platform, reason):
            await self._reset_runtime(platform)
            self._cleanup_profile_browser_processes(platform)
            current_url = url
            runtime = self._open_external_session_browser(platform, url)
            if not self._wait_for_external_debug_port(platform):
                raise RuntimeError(
                    "Boss 专用会话浏览器启动失败：未检测到调试端口。"
                    " 请先关闭残留的 Boss 专用浏览器窗口后再重试。"
                )
        else:
            try:
                current_url = await self.open_runtime_url(platform, url)
                runtime = "playwright"
            except Exception as first_error:
                logger.warning(
                    "open_url failed on current runtime page: platform=%s url=%s reason=%s error=%s",
                    platform,
                    url,
                    reason,
                    first_error,
                )
                try:
                    current_url = await self._navigate(platform, url, force_new_page=True)
                    runtime = "playwright"
                except Exception as second_error:
                    logger.warning(
                        "open_url failed on fresh page: platform=%s url=%s reason=%s error=%s",
                        platform,
                        url,
                        reason,
                        second_error,
                    )
                    try:
                        await self._reset_runtime(platform)
                        current_url = await self._navigate(
                            platform,
                            url,
                            force_new_page=True,
                        )
                        runtime = "playwright"
                    except Exception as third_error:
                        logger.warning(
                            "open_url fallback to external browser: platform=%s url=%s reason=%s error=%s",
                            platform,
                            url,
                            reason,
                            third_error,
                        )
                        webbrowser.open(url)
                        current_url = url
                        runtime = "external"
        payload = {
            "active": True,
            "storage_dir": str(storage_dir),
            "last_opened_url": current_url,
            "last_opened_reason": reason,
            "last_opened_at": datetime.utcnow().isoformat(),
            "runtime": runtime,
        }
        if reason == "search_verification":
            payload["search_ready"] = False
        return self._upsert_state(
            db,
            platform,
            payload,
        )

    async def fetch_json_with_session(
        self,
        platform: str,
        *,
        page_url: str,
        api_url: str,
        form_data: dict[str, str],
        headers: dict[str, str] | None = None,
        require_external_runtime: bool = False,
    ) -> dict[str, Any]:
        try:
            runtime = (
                await self._ensure_external_runtime(platform)
                if require_external_runtime
                else await self._ensure_runtime(platform)
            )
            return await self._fetch_json_with_runtime(
                runtime,
                page_url=page_url,
                api_url=api_url,
                form_data=form_data,
                headers=headers,
            )
        except Exception as error:
            runtime = self._runtimes.get(platform)
            if require_external_runtime or not runtime or runtime.engine != "external_edge_cdp":
                raise
            logger.warning(
                "fetch_json_with_session retrying after external CDP runtime failure: platform=%s error=%s",
                platform,
                error,
            )
            self._runtimes.pop(platform, None)
            runtime = await self._ensure_runtime(platform)
            return await self._fetch_json_with_runtime(
                runtime,
                page_url=page_url,
                api_url=api_url,
                form_data=form_data,
                headers=headers,
            )

    async def _fetch_json_with_runtime(
        self,
        runtime: BrowserRuntime,
        *,
        page_url: str,
        api_url: str,
        form_data: dict[str, str],
        headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        page = await self._ensure_work_page(runtime)
        if page.is_closed():
            page = runtime.work_page = await runtime.context.new_page()

        await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
        page_html = await page.content()
        current_page_url = page.url

        request_context = runtime.context.request

        response = await request_context.post(
            api_url,
            form=form_data,
            headers=headers or {},
            timeout=25000,
        )
        response_text = await response.text()

        return {
            "page_url": current_page_url,
            "page_html": page_html,
            "response_url": response.url,
            "response_status": response.status,
            "response_text": response_text,
        }

    def state(self, db: Session, platform: str) -> dict:
        setting = db.get(AppSetting, f"platform_session:{platform}")
        storage_dir = self.session_dir(platform)
        persisted_profile = self._has_persisted_profile(platform)
        if not setting:
            return {
                "active": persisted_profile,
                "search_ready": False,
                "storage_dir": str(storage_dir),
                "last_started_at": None,
            }
        runtime = self._runtimes.get(platform)
        runtime_alive = bool(runtime and not runtime.page.is_closed())
        stored_runtime = str(setting.value.get("runtime") or "")
        active = (bool(setting.value.get("active")) or persisted_profile) and (
            settings.disable_browser_open or runtime_alive
            or stored_runtime in {"external", "external_edge"}
            or persisted_profile
        )
        search_ready = bool(setting.value.get("search_ready")) and active
        return {
            "active": active,
            "search_ready": search_ready,
            "storage_dir": str(storage_dir),
            "last_started_at": setting.value.get("last_started_at"),
        }

    async def shutdown(self) -> None:
        async with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
            playwright = self._playwright
            self._playwright = None

        for runtime in runtimes:
            if runtime.managed_context:
                try:
                    await runtime.context.close()
                except Exception:
                    pass

        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass


browser_session_service = BrowserSessionService()
