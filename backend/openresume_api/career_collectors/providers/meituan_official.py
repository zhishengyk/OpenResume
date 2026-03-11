from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import math
from typing import Any
from urllib.parse import urlencode

import httpx


BASE_URL = "https://zhaopin.meituan.com"


@dataclass(frozen=True)
class MeituanVariantConfig:
    variant: str
    entry_url: str
    detail_query: dict[str, str]


VARIANT_CONFIGS: dict[str, MeituanVariantConfig] = {
    "experienced": MeituanVariantConfig(
        variant="experienced",
        entry_url="https://zhaopin.meituan.com/web/social",
        detail_query={"highlightType": "social"},
    ),
    "campus": MeituanVariantConfig(
        variant="campus",
        entry_url="https://zhaopin.meituan.com/web/campus",
        detail_query={"highlightType": "campus"},
    ),
}


class MeituanOfficialClient:
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

    def collect_jobs(
        self,
        *,
        variant: str,
        keywords: list[str],
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        deduped: dict[str, dict[str, Any]] = {}
        max_items = max(1, limit) if limit else None
        query_keywords = [item.strip() for item in keywords if item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        if not query_keywords:
            query_keywords = [""]

        with self._new_client(config.entry_url) as client:
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    keyword=keyword,
                    limit=max_items,
                ):
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("jobUnionId") or "")
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
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("jobUnionId") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
                    if max_items and len(deduped) >= max_items:
                        break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:max_items]

    def get_job_detail(
        self,
        *,
        variant: str,
        job_id: str,
    ) -> dict[str, Any]:
        return self.get_job_details(
            variant=variant,
            job_ids=[job_id],
            worker_count=1,
        ).get(job_id, {})

    def get_job_details(
        self,
        *,
        variant: str,
        job_ids: list[str],
        worker_count: int,
    ) -> dict[str, dict[str, Any]]:
        clean_ids = [str(item).strip() for item in job_ids if str(item).strip()]
        if not clean_ids:
            return {}
        chunk_count = min(max(1, worker_count), len(clean_ids))
        chunks = self._chunk_items(clean_ids, chunk_count)
        if len(chunks) <= 1:
            return self._fetch_detail_chunk(variant=variant, job_ids=clean_ids)

        details: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            for partial in executor.map(
                lambda chunk: self._fetch_detail_chunk(
                    variant=variant,
                    job_ids=chunk,
                ),
                chunks,
            ):
                details.update(partial)
        return details

    def detail_url(self, *, variant: str, job_id: str) -> str:
        config = VARIANT_CONFIGS[variant]
        query = {"jobUnionId": job_id, **config.detail_query}
        return f"{BASE_URL}/web/position/detail?{urlencode(query)}"

    def _matches_variant(self, *, variant: str, item: dict[str, Any]) -> bool:
        title_text = str(item.get("name") or "").casefold()
        job_type = str(item.get("jobType") or "").strip()
        special_code = str(item.get("jobSpecialCode") or "").strip()

        if variant == "experienced":
            if job_type or special_code:
                if job_type == "2" or special_code == "6":
                    return False
                if job_type == "3" or special_code == "5":
                    return True
            return "intern" not in title_text and "实习" not in title_text

        if variant == "internship":
            if job_type or special_code:
                return job_type == "2" or special_code == "6"
            return "intern" in title_text or "实习" in title_text

        return True

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
        keyword: str,
        limit: int | None,
    ) -> list[dict[str, Any]]:
        first_items, reported_total_pages = self._fetch_keyword_page(
            client,
            keyword=keyword,
            current=1,
        )
        if not first_items:
            return []

        items = list(first_items)
        if limit and len(items) >= limit:
            return items[:limit]

        total_pages = self._total_pages(
            reported_total_pages=reported_total_pages,
            limit=limit,
        )
        if total_pages <= 1 or len(first_items) < self.page_size:
            return items[:limit]

        remaining_pages = list(range(2, total_pages + 1))
        for page_items in self._fetch_remaining_pages(
            client,
            keyword=keyword,
            pages=remaining_pages,
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
        pages: list[int],
    ) -> list[list[dict[str, Any]]]:
        worker_count = min(self.page_worker_count, len(pages))
        if worker_count <= 1:
            return [
                self._fetch_keyword_page(
                    client,
                    keyword=keyword,
                    current=current,
                )[0]
                for current in pages
            ]

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(
                executor.map(
                    lambda current: (
                        current,
                        self._fetch_keyword_page(
                            client,
                            keyword=keyword,
                            current=current,
                        )[0],
                    ),
                    pages,
                )
            )
        results.sort(key=lambda item: item[0])
        return [page_items for _, page_items in results]

    def _fetch_keyword_page(
        self,
        client: httpx.Client,
        *,
        keyword: str,
        current: int,
    ) -> tuple[list[dict[str, Any]], int]:
        response = client.post(
            f"{BASE_URL}/api/official/job/getJobList",
            json=self._list_payload(current=current, keyword=keyword),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        page_items = data.get("list") or []
        if not isinstance(page_items, list):
            page_items = []
        page = data.get("page") or {}
        try:
            total_pages = int(page.get("totalPage") or 0)
        except (TypeError, ValueError):
            total_pages = 0
        return [item for item in page_items if isinstance(item, dict)], total_pages

    def _fetch_detail_chunk(
        self,
        *,
        variant: str,
        job_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        details: dict[str, dict[str, Any]] = {}
        with self._new_client(config.entry_url) as client:
            for job_id in job_ids:
                try:
                    response = client.post(
                        f"{BASE_URL}/api/official/job/getJobDetail",
                        json={"jobUnionId": job_id},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    data = payload.get("data")
                    details[job_id] = data if isinstance(data, dict) else {}
                except Exception:
                    details[job_id] = {}
        return details

    def _total_pages(self, *, reported_total_pages: int, limit: int | None) -> int:
        if reported_total_pages > 0:
            page_count = reported_total_pages
        else:
            page_count = self.max_pages
        if limit:
            page_count = min(page_count, math.ceil(limit / self.page_size))
        return max(1, min(self.max_pages, page_count))

    def _chunk_items(self, values: list[str], chunk_count: int) -> list[list[str]]:
        bucket_count = max(1, min(chunk_count, len(values)))
        chunks: list[list[str]] = [[] for _ in range(bucket_count)]
        for index, value in enumerate(values):
            chunks[index % bucket_count].append(value)
        return [chunk for chunk in chunks if chunk]

    def _list_payload(self, *, current: int, keyword: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "page": {
                "pageNo": current,
                "pageSize": self.page_size,
            }
        }
        if keyword:
            payload["keywords"] = keyword
        return payload

    def _sort_key(self, item: dict[str, Any]) -> int:
        for key in ("refreshTime", "firstPostTime"):
            try:
                return int(item.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return 0
