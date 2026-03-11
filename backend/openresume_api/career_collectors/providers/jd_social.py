from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import math
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
        page_worker_count: int = 1,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_pages = max(1, max_pages)
        self.page_size = max(1, page_size)
        self.page_worker_count = max(1, page_worker_count)
        self._transport = transport

    def collect_jobs(self, *, keywords: list[str], limit: int | None = None) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        max_items = max(1, limit) if limit else None
        query_keywords = [item.strip() for item in keywords if item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        if not query_keywords:
            query_keywords = [""]

        with self._new_client() as client:
            self._warmup(client)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    keyword=keyword,
                    limit=max_items,
                ):
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
                    if max_items and len(deduped) >= max_items:
                        break
                if max_items and len(deduped) >= max_items:
                    break

            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    keyword="",
                    limit=max_items,
                ):
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
                    if max_items and len(deduped) >= max_items:
                        break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:max_items]

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
        limit: int | None,
    ) -> list[dict[str, Any]]:
        first_page = self._fetch_keyword_page(client, keyword=keyword, page_index=1)
        if not first_page:
            return []

        items = list(first_page)
        page_count = self._page_budget(limit=limit)
        if page_count <= 1 or len(first_page) < self.page_size:
            return items[:limit]

        remaining_pages = list(range(2, page_count + 1))
        if not remaining_pages:
            return items

        for page_items in self._fetch_remaining_pages(
            client,
            keyword=keyword,
            page_indexes=remaining_pages,
        ):
            if not page_items:
                break
            items.extend(page_items)
            if limit and len(items) >= limit:
                break
            if len(page_items) < self.page_size:
                break
        return items[:limit]

    def _fetch_remaining_pages(
        self,
        client: httpx.Client,
        *,
        keyword: str,
        page_indexes: list[int],
    ) -> list[list[dict[str, Any]]]:
        worker_count = min(self.page_worker_count, len(page_indexes))
        if worker_count <= 1:
            return [
                self._fetch_keyword_page(client, keyword=keyword, page_index=page_index)
                for page_index in page_indexes
            ]

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(
                executor.map(
                    lambda page_index: (
                        page_index,
                        self._fetch_keyword_page(
                            client,
                            keyword=keyword,
                            page_index=page_index,
                        ),
                    ),
                    page_indexes,
                )
            )
        results.sort(key=lambda item: item[0])
        return [page_items for _, page_items in results]

    def _fetch_keyword_page(
        self,
        client: httpx.Client,
        *,
        keyword: str,
        page_index: int,
    ) -> list[dict[str, Any]]:
        response = client.post(
            f"{BASE_URL}/web/job/job_list",
            data={
                "pageIndex": page_index,
                "pageSize": self.page_size,
                "workCityJson": "[]",
                "jobTypeJson": "[]",
                "depTypeJson": "[]",
                "jobSearch": keyword,
            },
        )
        response.raise_for_status()
        return self._decode_list_payload(response)

    def _page_budget(self, limit: int | None) -> int:
        if not limit:
            return self.max_pages
        return max(1, min(self.max_pages, math.ceil(limit / self.page_size)))

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
