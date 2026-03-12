from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ApplyExecutionRequest:
    company_key: str
    apply_url: str
    execution_mode: str
    full_name: str
    headline: str
    resume_path: str
    storage_state_path: str


@dataclass(frozen=True)
class ApplyExecutionOutcome:
    status: str
    message: str
    verification_url: str | None = None
    launch_url: str | None = None
    context: dict[str, object] = field(default_factory=dict)


class AutomationPage(Protocol):
    async def goto(self, url: str) -> None: ...

    async def content_contains(self, markers: list[str]) -> bool: ...

    async def has_any(self, selectors: list[str]) -> str | None: ...

    async def evaluate(self, script: str) -> object: ...

    async def wait_for_timeout(self, milliseconds: int) -> None: ...

    async def try_set_input_files(
        self,
        selectors: list[str],
        file_path: str,
    ) -> str | None: ...

    async def try_fill(self, selectors: list[str], value: str) -> str | None: ...

    async def try_click(self, selectors: list[str]) -> str | None: ...


class AutomationRuntime(Protocol):
    async def run(
        self,
        *,
        storage_state_path: str,
        headless: bool,
        callback,
    ) -> ApplyExecutionOutcome: ...

    async def interactive_run(
        self,
        *,
        storage_state_path: str,
        callback,
        timeout_seconds: int = 300,
    ) -> None: ...
