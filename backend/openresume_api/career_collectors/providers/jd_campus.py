from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import math
from typing import Any

import httpx


BASE_URL = "https://campus.jd.com"


@dataclass(frozen=True)
class JdCampusVariantConfig:
    variant: str
    type_code: str
    entry_url: str


VARIANT_CONFIGS: dict[str, JdCampusVariantConfig] = {
    "campus": JdCampusVariantConfig(
        variant="campus",
        type_code="present",
        entry_url="https://campus.jd.com/#/jobs",
    ),
    "internship": JdCampusVariantConfig(
        variant="internship",
        type_code="internship",
        entry_url="https://campus.jd.com/#/jobs",
    ),
}


class JdCampusClient:
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

        with self._new_client(referer=config.entry_url) as client:
            self._warmup(client)
            self._load_dictionary(client, config=config)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
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
                    config=config,
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

    def get_job_detail(
        self,
        *,
        variant: str,
        publish_id: str,
    ) -> dict[str, Any]:
        config = VARIANT_CONFIGS[variant]
        with self._new_client(referer=config.entry_url) as client:
            response = client.post(
                f"{BASE_URL}/api/wx/position/detail/{publish_id}",
                json={},
            )
            response.raise_for_status()
        payload = response.json()
        detail = payload.get("body")
        return detail if isinstance(detail, dict) else {}

    def get_job_details(
        self,
        *,
        variant: str,
        publish_ids: list[str],
        worker_count: int,
    ) -> dict[str, dict[str, Any]]:
        clean_ids = [str(item).strip() for item in publish_ids if str(item).strip()]
        if not clean_ids:
            return {}
        chunk_count = min(max(1, worker_count), len(clean_ids))
        chunks = self._chunk_items(clean_ids, chunk_count)
        if len(chunks) <= 1:
            return self._fetch_detail_chunk(variant=variant, publish_ids=clean_ids)

        details: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            for partial in executor.map(
                lambda chunk: self._fetch_detail_chunk(
                    variant=variant,
                    publish_ids=chunk,
                ),
                chunks,
            ):
                details.update(partial)
        return details

    def detail_url(self, *, variant: str, publish_id: str) -> str:
        type_code = VARIANT_CONFIGS[variant].type_code
        if publish_id:
            return f"{BASE_URL}/#/jobs?type={type_code}&publishId={publish_id}"
        return f"{BASE_URL}/#/jobs?type={type_code}"

    def _fetch_detail_chunk(
        self,
        *,
        variant: str,
        publish_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        details: dict[str, dict[str, Any]] = {}
        with self._new_client(referer=config.entry_url) as client:
            for publish_id in publish_ids:
                response = client.post(
                    f"{BASE_URL}/api/wx/position/detail/{publish_id}",
                    json={},
                )
                response.raise_for_status()
                payload = response.json()
                detail = payload.get("body")
                details[publish_id] = detail if isinstance(detail, dict) else {}
        return details

    def _new_client(self, *, referer: str) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json; charset=UTF-8",
                "Origin": BASE_URL,
                "Referer": referer,
            },
            transport=self._transport,
            trust_env=False,
        )

    def _warmup(self, client: httpx.Client) -> None:
        try:
            client.get(f"{BASE_URL}/api/wx/position/getProjectList")
        except Exception:
            return

    def _load_dictionary(
        self,
        client: httpx.Client,
        *,
        config: JdCampusVariantConfig,
    ) -> None:
        try:
            client.post(
                f"{BASE_URL}/api/wx/position/dict",
                params={"type": config.type_code},
                json=[],
            )
        except Exception:
            return

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: JdCampusVariantConfig,
        keyword: str,
        limit: int | None,
    ) -> list[dict[str, Any]]:
        first_items, total = self._fetch_keyword_page(
            client,
            config=config,
            keyword=keyword,
            page_index=0,
        )
        if not first_items:
            return []

        items = list(first_items)
        total_pages = self._total_pages(total=total, limit=limit)
        if total_pages <= 1 or len(first_items) < self.page_size:
            return items[:limit]

        remaining_pages = list(range(1, total_pages))
        for page_items in self._fetch_remaining_pages(
            client,
            config=config,
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
        config: JdCampusVariantConfig,
        keyword: str,
        page_indexes: list[int],
    ) -> list[list[dict[str, Any]]]:
        worker_count = min(self.page_worker_count, len(page_indexes))
        if worker_count <= 1:
            return [
                self._fetch_keyword_page(
                    client,
                    config=config,
                    keyword=keyword,
                    page_index=page_index,
                )[0]
                for page_index in page_indexes
            ]

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(
                executor.map(
                    lambda page_index: (
                        page_index,
                        self._fetch_keyword_page(
                            client,
                            config=config,
                            keyword=keyword,
                            page_index=page_index,
                        )[0],
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
        config: JdCampusVariantConfig,
        keyword: str,
        page_index: int,
    ) -> tuple[list[dict[str, Any]], int]:
        response = client.post(
            f"{BASE_URL}/api/wx/position/page",
            params={"type": config.type_code},
            json={
                "pageSize": self.page_size,
                "pageIndex": page_index,
                "parameter": {
                    "positionName": keyword,
                    "planIdList": [],
                    "jobDirectionCodeList": [],
                    "workCityCodeList": [],
                    "positionDeptList": [],
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        body = payload.get("body") or {}
        page_items = body.get("items") or []
        if not isinstance(page_items, list):
            page_items = []
        try:
            total = int(body.get("totalNumber") or 0)
        except (TypeError, ValueError):
            total = 0
        return [item for item in page_items if isinstance(item, dict)], total

    def _total_pages(self, *, total: int, limit: int | None) -> int:
        if total > 0:
            page_count = math.ceil(total / self.page_size)
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

    def _job_id(self, item: dict[str, Any]) -> str:
        for key in ("publishId", "reqId"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return ""

    def _sort_key(self, item: dict[str, Any]) -> int:
        try:
            return int(item.get("publishTime") or 0)
        except (TypeError, ValueError):
            return 0
