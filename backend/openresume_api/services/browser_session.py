from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
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


class BrowserSessionService:
    def __init__(self) -> None:
        self._playwright = None
        self._runtimes: dict[str, BrowserRuntime] = {}
        self._lock = asyncio.Lock()

    def session_dir(self, platform: str) -> Path:
        directory = settings.browser_dir / platform
        directory.mkdir(parents=True, exist_ok=True)
        return directory

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
            context, engine = await self._launch_context(playwright, platform)
            page = context.pages[0] if context.pages else await context.new_page()
            runtime = BrowserRuntime(context=context, page=page, engine=engine)
            self._runtimes[platform] = runtime
            return runtime

    async def _launch_context(self, playwright, platform: str) -> tuple[BrowserContext, str]:
        launch_options = {
            "user_data_dir": str(self.session_dir(platform)),
            "headless": settings.disable_browser_open,
            "viewport": {"width": 1440, "height": 960},
        }
        errors: list[str] = []

        for engine, extra_options in (
            ("chromium", {}),
            ("msedge", {"channel": "msedge"}),
        ):
            try:
                context = await playwright.chromium.launch_persistent_context(
                    **launch_options,
                    **extra_options,
                )
                return context, engine
            except Exception as error:
                errors.append(f"{engine}: {error}")

        joined = " | ".join(errors)
        raise RuntimeError(
            "Playwright \u65e0\u6cd5\u542f\u52a8 Chromium \u6216 Microsoft Edge\u3002"
            " \u5982\u679c\u4f60\u5e0c\u671b\u4f7f\u7528 Playwright \u81ea\u5e26 Chromium\uff0c"
            " \u8bf7\u6267\u884c `python -m playwright install chromium`\u3002"
            f" \u5f53\u524d\u9519\u8bef\uff1a{joined}"
        )

    async def _ensure_page(self, platform: str) -> Page:
        runtime = await self._ensure_runtime(platform)
        if runtime.page.is_closed():
            runtime.page = (
                runtime.context.pages[0]
                if runtime.context.pages
                else await runtime.context.new_page()
            )
        return runtime.page

    def _has_runtime(self, platform: str) -> bool:
        runtime = self._runtimes.get(platform)
        return bool(runtime and not runtime.page.is_closed())

    async def _reset_runtime(self, platform: str) -> None:
        runtime = self._runtimes.pop(platform, None)
        if not runtime:
            return
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
        except PlaywrightTimeoutError:
            # Fallback to client-side assignment; some login pages keep redirecting during challenge.
            try:
                await page.evaluate(
                    "target => { window.location.href = target; }",
                    url,
                )
                await page.wait_for_timeout(600)
            except Exception:
                pass

        current_url = page.url or ""
        if current_url.startswith("about:blank"):
            try:
                await page.evaluate(
                    "target => { window.location.href = target; }",
                    url,
                )
                await page.wait_for_timeout(600)
                current_url = page.url or ""
            except Exception:
                current_url = ""

        if not settings.disable_browser_open:
            await page.bring_to_front()
        if not current_url or current_url.startswith("about:blank"):
            raise RuntimeError(f"session navigate failed, stayed on about:blank for {url}")
        return current_url

    async def start(self, db: Session, platform: str, login_url: str) -> dict:
        storage_dir = self.session_dir(platform)
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

        try:
            # Session start always uses a fresh page to avoid reusing stale about:blank tabs.
            current_url = await self._navigate(
                platform,
                login_url,
                force_new_page=True,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            runtime = "playwright"
        except Exception as first_error:
            logger.warning(
                "session start navigate failed on first attempt: platform=%s url=%s error=%s",
                platform,
                login_url,
                first_error,
            )
            try:
                # Retry once with the default navigation strategy before falling back.
                current_url = await self._navigate(platform, login_url, force_new_page=True)
                runtime = "playwright"
            except Exception as second_error:
                logger.warning(
                    "session start navigate failed on second attempt: platform=%s url=%s error=%s",
                    platform,
                    login_url,
                    second_error,
                )
                try:
                    await self._reset_runtime(platform)
                    current_url = await self._navigate(platform, login_url, force_new_page=True)
                    runtime = "playwright"
                except Exception as third_error:
                    logger.warning(
                        "session start fallback to external browser: platform=%s url=%s error=%s",
                        platform,
                        login_url,
                        third_error,
                    )
                    webbrowser.open(login_url)
                    current_url = login_url
                    runtime = "external"

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
    ) -> dict[str, Any]:
        runtime = await self._ensure_runtime(platform)
        request_context = runtime.context.request

        page_response = await request_context.get(
            page_url,
            timeout=25000,
        )
        page_html = await page_response.text()
        current_page_url = page_response.url

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
        if not setting:
            return {
                "active": False,
                "search_ready": False,
                "storage_dir": str(storage_dir),
                "last_started_at": None,
            }
        runtime = self._runtimes.get(platform)
        runtime_alive = bool(runtime and not runtime.page.is_closed())
        active = bool(setting.value.get("active")) and (
            settings.disable_browser_open or runtime_alive
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
