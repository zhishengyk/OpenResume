from __future__ import annotations

from typing import Any

import httpx


BASE_URL = "https://zhaopin.jd.com"


class JdSocialClient:
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

    def collect_jobs(self, *, keywords: list[str]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        query_keywords = [item.strip() for item in keywords if item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        if not query_keywords:
            query_keywords = [""]

        with self._new_client() as client:
            self._warmup(client)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(client, keyword=keyword):
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)

            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(client, keyword=""):
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def detail_url(self, *, job_id: str) -> str:
        if job_id:
            return f"{BASE_URL}/web/job_info_list/3?jobId={job_id}"
        return f"{BASE_URL}/web/job_info_list/3"

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/web/job",
                "X-Requested-With": "XMLHttpRequest",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _warmup(self, client: httpx.Client) -> None:
        try:
            client.get(f"{BASE_URL}/web/job")
        except Exception:
            return

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.post(
                f"{BASE_URL}/web/job/job_list",
                data={
                    "pageIndex": current,
                    "pageSize": self.page_size,
                    "workCityJson": "[]",
                    "jobTypeJson": "[]",
                    "depTypeJson": "[]",
                    "jobSearch": keyword,
                },
            )
            response.raise_for_status()
            page_items = self._decode_list_payload(response)
            if not page_items:
                break
            items.extend(page_items)
            if len(page_items) < self.page_size:
                break
        return items

    def _decode_list_payload(self, response: httpx.Response) -> list[dict[str, Any]]:
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("result", "data", "list", "rows"):
                values = payload.get(key)
                if isinstance(values, list):
                    return [item for item in values if isinstance(item, dict)]
                if isinstance(values, dict):
                    nested = values.get("list") or values.get("rows") or values.get("items")
                    if isinstance(nested, list):
                        return [item for item in nested if isinstance(item, dict)]
        return []

    def _job_id(self, item: dict[str, Any]) -> str:
        for key in ("requirementId", "positionId", "id"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return ""

    def _sort_key(self, item: dict[str, Any]) -> int:
        try:
            return int(item.get("publishTime") or 0)
        except (TypeError, ValueError):
            return 0
