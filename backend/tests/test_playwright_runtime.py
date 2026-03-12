import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from openresume_api.automation.playwright_runtime import (
    DESKTOP_VIEWPORT,
    INTERACTIVE_BROWSER_ARGS,
    PlaywrightAutomationRuntime,
)


class FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, str]] = []

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        self.goto_calls.append((url, wait_until))

    async def content(self) -> str:
        return ""


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()
        self.storage_state_paths: list[str] = []
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.page

    async def storage_state(self, *, path: str) -> None:
        self.storage_state_paths.append(path)

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.new_context_calls: list[dict[str, object]] = []
        self.contexts: list[FakeContext] = []
        self.handlers: dict[str, object] = {}
        self.closed = False

    async def new_context(self, **kwargs) -> FakeContext:
        self.new_context_calls.append(kwargs)
        context = FakeContext()
        self.contexts.append(context)
        return context

    def on(self, event: str, handler) -> None:
        self.handlers[event] = handler

    def is_connected(self) -> bool:
        return not self.closed

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self) -> None:
        self.launch_calls: list[dict[str, object]] = []
        self.browsers: list[FakeBrowser] = []

    async def launch(self, **kwargs) -> FakeBrowser:
        self.launch_calls.append(kwargs)
        browser = FakeBrowser()
        self.browsers.append(browser)
        return browser


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()


class FakeAsyncPlaywright:
    def __init__(self, playwright: FakePlaywright) -> None:
        self._playwright = playwright

    async def __aenter__(self) -> FakePlaywright:
        return self._playwright

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def install_fake_playwright(monkeypatch, fake_playwright: FakePlaywright) -> None:
    module = SimpleNamespace(
        async_playwright=lambda: FakeAsyncPlaywright(fake_playwright)
    )
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)


def test_interactive_run_uses_maximized_browser_and_no_viewport(tmp_path, monkeypatch):
    runtime = PlaywrightAutomationRuntime()
    fake_playwright = FakePlaywright()
    install_fake_playwright(monkeypatch, fake_playwright)

    state_path = tmp_path / "storage-state.json"
    state_path.write_text("{}", encoding="utf-8")

    async def callback(page) -> None:
        return None

    async def completion_callback() -> bool:
        return True

    asyncio.run(
        runtime.interactive_run(
            storage_state_path=str(state_path),
            callback=callback,
            completion_callback=completion_callback,
            timeout_seconds=1,
        )
    )

    assert fake_playwright.chromium.launch_calls == [
        {"headless": False, "args": list(INTERACTIVE_BROWSER_ARGS)}
    ]
    browser = fake_playwright.chromium.browsers[0]
    assert browser.new_context_calls == [
        {"storage_state": str(state_path), "no_viewport": True}
    ]
    assert browser.contexts[0].storage_state_paths[-1] == str(state_path)


def test_interactive_capture_uses_maximized_browser_and_no_viewport(
    tmp_path, monkeypatch
):
    runtime = PlaywrightAutomationRuntime()
    fake_playwright = FakePlaywright()
    install_fake_playwright(monkeypatch, fake_playwright)

    state_path = tmp_path / "storage-state.json"

    asyncio.run(
        runtime.interactive_capture(
            storage_state_path=str(state_path),
            target_url="https://careers.tencent.com/login.html",
            timeout_seconds=0,
        )
    )

    assert fake_playwright.chromium.launch_calls == [
        {"headless": False, "args": list(INTERACTIVE_BROWSER_ARGS)}
    ]
    browser = fake_playwright.chromium.browsers[0]
    assert browser.new_context_calls == [{"no_viewport": True}]
    assert browser.contexts[0].page.goto_calls == [
        ("https://careers.tencent.com/login.html", "domcontentloaded")
    ]


def test_inspect_uses_desktop_viewport_for_headless_checks(tmp_path, monkeypatch):
    runtime = PlaywrightAutomationRuntime()
    fake_playwright = FakePlaywright()
    install_fake_playwright(monkeypatch, fake_playwright)

    state_path = tmp_path / "storage-state.json"

    async def callback(page) -> tuple[bool, str]:
        return True, "ok"

    result = asyncio.run(
        runtime.inspect(
            storage_state_path=str(state_path),
            headless=True,
            callback=callback,
        )
    )

    assert result == (True, "ok")
    assert fake_playwright.chromium.launch_calls == [{"headless": True}]
    browser = fake_playwright.chromium.browsers[0]
    assert browser.new_context_calls == [{"viewport": dict(DESKTOP_VIEWPORT)}]
    assert browser.contexts[0].storage_state_paths[-1] == str(state_path)
