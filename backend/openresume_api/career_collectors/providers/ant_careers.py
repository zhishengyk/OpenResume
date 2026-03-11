from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from typing import Any

import httpx


BASE_URL = "https://hrcareersweb.antgroup.com"


@dataclass(frozen=True)
class AntCareerVariantConfig:
    variant: str
    entry_url: str
    search_path: str
    detail_path: str
    channel: str
    detail_url_template: str
    recruit_types: tuple[str, ...] = ()


VARIANT_CONFIGS: dict[str, AntCareerVariantConfig] = {
    "experienced": AntCareerVariantConfig(
        variant="experienced",
        entry_url="https://talent.antgroup.com/off-campus",
        search_path="/api/social/position/search",
        detail_path="/api/social/position/detail",
        channel="group_official_site",
        detail_url_template=(
            "https://talent.antgroup.com/off-campus-position?positionId={job_id}"
        ),
        recruit_types=(),
    ),
    "campus": AntCareerVariantConfig(
        variant="campus",
        entry_url="https://talent.antgroup.com/campus-full-list",
        search_path="/api/campus/position/search",
        detail_path="/api/campus/position/detail",
        channel="campus_group_official_site",
        detail_url_template="https://talent.antgroup.com/campus-position?positionId={job_id}",
        recruit_types=("campus_graduates",),
    ),
    "internship": AntCareerVariantConfig(
        variant="internship",
        entry_url="https://talent.antgroup.com/campus-full-list",
        search_path="/api/campus/position/search",
        detail_path="/api/campus/position/detail",
        channel="campus_group_official_site",
        detail_url_template="https://talent.antgroup.com/campus-position?positionId={job_id}",
        recruit_types=("campus_intern", "campus_talent_plan"),
    ),
}


class AntCareerClient:
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
        # Ant APIs currently return empty content for oversized pageSize values.
        self.page_size = max(1, min(10, page_size))
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

        with self._new_client() as client:
            self._warmup_search_conditions(client, config=config)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                    limit=max_items,
                ):
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    if (
                        config.variant == "internship"
                        and not self._looks_like_internship(item)
                    ):
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
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    if (
                        config.variant == "internship"
                        and not self._looks_like_internship(item)
                    ):
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
        config = VARIANT_CONFIGS[variant]
        with self._new_client() as client:
            payload = self._post_json(
                client,
                path=config.detail_path,
                referer=config.entry_url,
                json_body={
                    "channel": config.channel,
                    "language": "zh",
                    "id": int(job_id),
                },
            )
        detail = payload.get("content")
        return detail if isinstance(detail, dict) else {}

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

    def detail_url(self, *, variant: str, job_id: str, position_url: str = "") -> str:
        if position_url:
            if position_url.startswith(("http://", "https://")):
                return position_url
            if position_url.startswith("/"):
                return f"https://talent.antgroup.com{position_url}"
        return VARIANT_CONFIGS[variant].detail_url_template.format(job_id=job_id)

    def _fetch_detail_chunk(
        self,
        *,
        variant: str,
        job_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        details: dict[str, dict[str, Any]] = {}
        with self._new_client() as client:
            for job_id in job_ids:
                payload = self._post_json(
                    client,
                    path=config.detail_path,
                    referer=config.entry_url,
                    json_body={
                        "channel": config.channel,
                        "language": "zh",
                        "id": int(job_id),
                    },
                )
                detail = payload.get("content")
                details[job_id] = detail if isinstance(detail, dict) else {}
        return details

    def parse_datetime(self, value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(UTC).replace(tzinfo=None)
        return dt

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _warmup_search_conditions(
        self,
        client: httpx.Client,
        *,
        config: AntCareerVariantConfig,
    ) -> None:
        try:
            self._post_json(
                client,
                path="/api/searchCondition/list",
                referer=config.entry_url,
                json_body={
                    "channel": config.channel,
                    "language": "zh",
                },
            )
        except Exception:
            return

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: AntCareerVariantConfig,
        keyword: str,
        limit: int | None,
    ) -> list[dict[str, Any]]:
        first_items, total = self._fetch_keyword_page(
            client,
            config=config,
            keyword=keyword,
            current=1,
        )
        if not first_items:
            return []

        items = list(first_items)
        total_pages = self._total_pages(total=total, limit=limit)
        if total_pages <= 1 or len(first_items) < self.page_size:
            return items[:limit]

        remaining_pages = list(range(2, total_pages + 1))
        for page_items in self._fetch_remaining_pages(
            client,
            config=config,
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
        config: AntCareerVariantConfig,
        keyword: str,
        pages: list[int],
    ) -> list[list[dict[str, Any]]]:
        worker_count = min(self.page_worker_count, len(pages))
        if worker_count <= 1:
            return [
                self._fetch_keyword_page(
                    client,
                    config=config,
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
                            config=config,
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
        config: AntCareerVariantConfig,
        keyword: str,
        current: int,
    ) -> tuple[list[dict[str, Any]], int]:
        payload = self._post_json(
            client,
            path=config.search_path,
            referer=config.entry_url,
            json_body=self._search_payload(
                config=config,
                current=current,
                keyword=keyword,
            ),
        )
        page_items = payload.get("content") or []
        if not isinstance(page_items, list):
            page_items = []
        try:
            total = int(payload.get("totalCount") or 0)
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

    def _post_json(
        self,
        client: httpx.Client,
        *,
        path: str,
        referer: str,
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        response = client.post(
            f"{BASE_URL}{path}",
            json=json_body,
            headers={
                "Origin": "https://talent.antgroup.com",
                "Referer": referer,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _search_payload(
        self,
        *,
        config: AntCareerVariantConfig,
        current: int,
        keyword: str,
    ) -> dict[str, Any]:
        if config.variant == "experienced":
            return {
                "key": keyword,
                "regions": "",
                "categories": "",
                "subCategories": "",
                "bgCode": "",
                "socialQrCode": "",
                "pageIndex": current,
                "pageSize": self.page_size,
                "channel": config.channel,
                "language": "zh",
            }
        return {
            "channel": config.channel,
            "language": "zh",
            "searchKey": keyword,
            "regions": "",
            "subCategories": "",
            "bgCode": "",
            "pageIndex": current,
            "pageSize": self.page_size,
            "recruitType": list(config.recruit_types),
            "batchIds": [],
        }

    def _looks_like_internship(self, payload: dict[str, Any]) -> bool:
        marker = " ".join(
            str(payload.get(key) or "")
            for key in ("name", "batchName", "project", "positionType", "categoryName")
        ).lower()
        return "实习" in marker or "intern" in marker

    def _sort_key(self, item: dict[str, Any]) -> int:
        publish_time = self.parse_datetime(item.get("publishTime"))
        if publish_time is None:
            return 0
        return int(publish_time.timestamp())
