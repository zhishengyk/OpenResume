from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx


CTRIP_BASE_URL = "https://job.ctrip.com"
_LIST_API_PATH = "/api/hrrecruit/getJobAd"
_INTERN_MARKERS = ("intern", "\u5b9e\u4e60")


def parse_ctrip_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class CtripVariantConfig:
    variant: str
    category: int
    entry_url: str
    detail_path: str


VARIANT_CONFIGS: dict[str, CtripVariantConfig] = {
    "experienced": CtripVariantConfig(
        variant="experienced",
        category=1,
        entry_url="https://job.ctrip.com/experienced/jobList",
        detail_path="/experienced/job-detail/{job_id}",
    ),
    "campus": CtripVariantConfig(
        variant="campus",
        category=2,
        entry_url="https://job.ctrip.com/campus/jobList",
        detail_path="/campus/job-detail/{job_id}",
    ),
    "internship": CtripVariantConfig(
        variant="internship",
        category=2,
        entry_url="https://job.ctrip.com/campus/jobList",
        detail_path="/campus/job-detail/{job_id}",
    ),
}


class CtripCareerClient:
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
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        query_keywords = self._normalized_keywords(keywords)
        max_items = max(1, limit) if limit else None
        deduped: dict[str, dict[str, Any]] = {}

        with self._new_client(config.entry_url) as client:
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                ):
                    if not self._matches_variant(variant=variant, payload=item):
                        continue
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(
                        job_id,
                        {
                            **item,
                            "__source_site": "job.ctrip.com",
                        },
                    )
                    if max_items and len(deduped) >= max_items:
                        break
                if max_items and len(deduped) >= max_items:
                    break

            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword="",
                ):
                    if not self._matches_variant(variant=variant, payload=item):
                        continue
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(
                        job_id,
                        {
                            **item,
                            "__source_site": "job.ctrip.com",
                        },
                    )
                    if max_items and len(deduped) >= max_items:
                        break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:max_items]

    def get_job_detail(self, *, job_id: str) -> dict[str, Any]:
        with self._new_client("https://job.ctrip.com/") as client:
            payload = self._post_json(
                client,
                json_body={"condition": {"fromId": [job_id]}},
            )
        items = ((payload.get("retValue") or {}).get("recruitJobAdList")) or []
        if not isinstance(items, list) or not items:
            return {}
        detail = items[0]
        return detail if isinstance(detail, dict) else {}

    def detail_url(self, *, variant: str, job_id: str) -> str:
        config = VARIANT_CONFIGS[variant]
        if job_id:
            return f"{CTRIP_BASE_URL}{config.detail_path.format(job_id=quote(job_id, safe=''))}"
        return config.entry_url

    def _new_client(self, referer: str) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": CTRIP_BASE_URL,
                "Referer": referer,
            },
            transport=self._transport,
            trust_env=False,
        )

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: CtripVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            payload = self._post_json(
                client,
                json_body={
                    "condition": {
                        "category": config.category,
                        "currentPage": current,
                        "pageSize": self.page_size,
                        "key": keyword,
                    }
                },
            )
            if str(payload.get("retCode") or "") not in {"201", "200"}:
                break

            value = payload.get("retValue") or {}
            page_items = value.get("recruitJobAdList") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))

            total = self._as_int(value.get("total"))
            if total and current * self.page_size >= total:
                break
        return items

    def _post_json(
        self,
        client: httpx.Client,
        *,
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        response = client.post(f"{CTRIP_BASE_URL}{_LIST_API_PATH}", json=json_body)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _matches_variant(self, *, variant: str, payload: dict[str, Any]) -> bool:
        if variant == "experienced":
            return True

        kind_name = str(payload.get("kindName") or "").casefold()
        title = str(payload.get("jobTitle") or "").casefold()
        marker = any(token in kind_name or token in title for token in _INTERN_MARKERS)

        if variant == "internship":
            return marker
        return not marker

    def _job_id(self, payload: dict[str, Any]) -> str:
        for key in ("fromId", "id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return ""

    def _normalized_keywords(self, keywords: list[str]) -> list[str]:
        query_keywords = [item.strip() for item in keywords if item and item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        return query_keywords or [""]

    def _sort_key(self, payload: dict[str, Any]) -> tuple[int, int]:
        posted_at = parse_ctrip_date(payload.get("publishDate"))
        date_ts = int(posted_at.timestamp()) if posted_at else 0
        return date_ts, self._as_int(payload.get("id"))

    def _as_int(self, value: Any) -> int:
        try:
            return int(str(value or "0"))
        except (TypeError, ValueError):
            return 0
