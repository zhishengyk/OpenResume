from __future__ import annotations

from collections.abc import Awaitable, Callable
import asyncio
from pathlib import Path
from typing import TypeVar

from .base import ApplyExecutionOutcome, AutomationPage

ResultT = TypeVar("ResultT")


class PlaywrightAutomationPage:
    def __init__(self, page) -> None:
        self._page = page

    async def goto(self, url: str) -> None:
        await self._page.goto(url, wait_until="domcontentloaded")

    async def current_url(self) -> str:
        return self._page.url or ""

    async def content_contains(self, markers: list[str]) -> bool:
        if not markers:
            return False
        content = (await self._page.content()).casefold()
        return any(marker.casefold() in content for marker in markers if marker.strip())

    async def has_any(self, selectors: list[str]) -> str | None:
        for selector in selectors:
            if not selector.strip():
                continue
            try:
                locator = self._page.locator(selector).first
                if await locator.count() > 0:
                    return selector
            except Exception:
                continue
        return None

    async def evaluate(self, script: str) -> object:
        return await self._page.evaluate(script)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        await self._page.wait_for_timeout(milliseconds)

    async def try_set_input_files(
        self,
        selectors: list[str],
        file_path: str,
    ) -> str | None:
        if not file_path:
            return None
        for selector in selectors:
            if not selector.strip():
                continue
            try:
                locator = self._page.locator(selector).first
                if await locator.count() == 0:
                    continue
                await locator.set_input_files(file_path)
                return selector
            except Exception:
                continue
        return None

    async def try_fill(self, selectors: list[str], value: str) -> str | None:
        if not value:
            return None
        for selector in selectors:
            if not selector.strip():
                continue
            try:
                locator = self._page.locator(selector).first
                if await locator.count() == 0:
                    continue
                await locator.fill(value)
                return selector
            except Exception:
                continue
        return None

    async def try_click(self, selectors: list[str]) -> str | None:
        for selector in selectors:
            if not selector.strip():
                continue
            try:
                locator = self._page.locator(selector).first
                if await locator.count() == 0:
                    continue
                await locator.click()
                return selector
            except Exception:
                continue
        return None


class PlaywrightAutomationRuntime:
    async def inspect(
        self,
        *,
        storage_state_path: str,
        headless: bool,
        callback: Callable[[AutomationPage], Awaitable[ResultT]],
    ) -> ResultT:
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:  # pragma: no cover - depends on optional install
            raise RuntimeError(
                "Playwright is not installed. Install backend optional dependency '[automation]'."
            ) from error

        state_path = Path(storage_state_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless)
            context_kwargs = {}
            if state_path.exists():
                context_kwargs["storage_state"] = str(state_path)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            try:
                result = await callback(PlaywrightAutomationPage(page))
                await context.storage_state(path=str(state_path))
                return result
            finally:
                await context.close()
                await browser.close()

    async def run(
        self,
        *,
        storage_state_path: str,
        headless: bool,
        callback: Callable[[AutomationPage], Awaitable[ApplyExecutionOutcome]],
    ) -> ApplyExecutionOutcome:
        return await self.inspect(
            storage_state_path=storage_state_path,
            headless=headless,
            callback=callback,
        )

    async def interactive_capture(
        self,
        *,
        storage_state_path: str,
        target_url: str,
        timeout_seconds: int = 300,
    ) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:  # pragma: no cover - depends on optional install
            raise RuntimeError(
                "Playwright is not installed. Install backend optional dependency '[automation]'."
            ) from error

        state_path = Path(storage_state_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context_kwargs = {}
            if state_path.exists():
                context_kwargs["storage_state"] = str(state_path)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            done = asyncio.get_running_loop().create_future()
            browser.on(
                "disconnected",
                lambda: None if done.done() else done.set_result(None),
            )
            try:
                await page.goto(target_url, wait_until="domcontentloaded")
                try:
                    await asyncio.wait_for(done, timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    pass
                await context.storage_state(path=str(state_path))
            finally:
                await context.close()
                if browser.is_connected():
                    await browser.close()

    async def interactive_run(
        self,
        *,
        storage_state_path: str,
        callback: Callable[[AutomationPage], Awaitable[object | None]],
        completion_callback: Callable[[], Awaitable[bool]] | None = None,
        completion_poll_ms: int = 1000,
        timeout_seconds: int = 300,
    ) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:  # pragma: no cover - depends on optional install
            raise RuntimeError(
                "Playwright is not installed. Install backend optional dependency '[automation]'."
            ) from error

        state_path = Path(storage_state_path)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context_kwargs = {}
            if state_path.exists():
                context_kwargs["storage_state"] = str(state_path)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
            done = asyncio.get_running_loop().create_future()
            browser.on(
                "disconnected",
                lambda: None if done.done() else done.set_result(None),
            )
            try:
                await callback(PlaywrightAutomationPage(page))
                deadline = asyncio.get_running_loop().time() + timeout_seconds
                poll_seconds = max(completion_poll_ms, 200) / 1000
                while not done.done():
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(done),
                            timeout=min(poll_seconds, remaining),
                        )
                        break
                    except asyncio.TimeoutError:
                        if not completion_callback:
                            continue
                        await context.storage_state(path=str(state_path))
                        if await completion_callback():
                            break
                await context.storage_state(path=str(state_path))
            finally:
                await context.close()
                if browser.is_connected():
                    await browser.close()


playwright_automation_runtime = PlaywrightAutomationRuntime()
