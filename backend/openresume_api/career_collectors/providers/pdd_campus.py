from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx


BASE_URL = "https://careers.pddglobalhr.com"
API_PREFIX = "/api/careers"


@dataclass(frozen=True)
class PddVariantConfig:
    variant: str
    entry_url: str
    list_path: str
    detail_url_path: str


VARIANT_CONFIGS: dict[str, PddVariantConfig] = {
    "campus": PddVariantConfig(
        variant="campus",
        entry_url="https://careers.pddglobalhr.com/campus/grad",
        list_path="/api/recruit/position/list",
        detail_url_path="/campus/grad/detail",
    ),
    "internship": PddVariantConfig(
        variant="internship",
        entry_url="https://careers.pddglobalhr.com/campus/intern",
        list_path="/api/recruit/position/train/list",
        detail_url_path="/campus/intern/detail",
    ),
}


class PddCampusClient:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        user_agent: str,
        max_pages: int,
        page_size: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_pages = max(1, max_pages)
        self.page_size = max(1, page_size)
        self._transport = transport

    def collect_jobs(
        self,
        *,
        variant: str,
        keywords: list[str],
    ) -> list[dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        deduped: dict[str, dict[str, Any]] = {}
        query_keywords = [item.strip() for item in keywords if item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        if not query_keywords:
            query_keywords = [""]

        with self._new_client(config.entry_url) as client:
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                ):
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword="",
                ):
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def get_job_detail(self, *, variant: str, job_id: str) -> dict[str, Any]:
        config = VARIANT_CONFIGS[variant]
        with self._new_client(config.entry_url) as client:
            response = client.post(
                self._api_url("/api/recruit/position/detail"),
                json={"id": job_id, "t": None},
            )
            response.raise_for_status()
        payload = response.json()
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    def detail_url(self, *, variant: str, job_id: str) -> str:
        config = VARIANT_CONFIGS[variant]
        return f"{BASE_URL}{config.detail_url_path}?{urlencode({'positionId': job_id})}"

    def _new_client(self, referer: str) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Referer": referer,
                "Origin": BASE_URL,
                "Content-Type": "application/json",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: PddVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.post(
                self._api_url(config.list_path),
                json=self._list_payload(current=current, keyword=keyword),
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result") or {}
            page_items = result.get("list") or []
            if not isinstance(page_items, list) or not page_items:
                break

            items.extend(item for item in page_items if isinstance(item, dict))
            try:
                total = int(result.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            if total and current * self.page_size >= total:
                break
        return items

    def _api_url(self, path: str) -> str:
        return f"{BASE_URL}{API_PREFIX}{path}"

    def _list_payload(self, *, current: int, keyword: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "page": current,
            "pageSize": self.page_size,
            "t": None,
        }
        if keyword:
            payload["name"] = keyword
        return payload

    def _sort_key(self, item: dict[str, Any]) -> int:
        try:
            return int(item.get("releaseTime") or 0)
        except (TypeError, ValueError):
            return 0
