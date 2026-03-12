from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from typing import Any
from urllib.parse import quote

import httpx


TME_BASE_URL = "https://join.tencentmusic.com"
_INTERN_MARKERS = ("intern", "\u5b9e\u4e60")


def parse_tme_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    match = re.search(r"(\d+)\s*\u5929\u524d", text)
    if match:
        return datetime.utcnow() - timedelta(days=int(match.group(1)))
    if text in {"\u4eca\u5929", "today"}:
        return datetime.utcnow()
    if text in {"\u6628\u5929", "yesterday"}:
        return datetime.utcnow() - timedelta(days=1)

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


@dataclass(frozen=True)
class TmeVariantConfig:
    variant: str
    entry_url: str
    list_path: str
    detail_path: str
    family: str


VARIANT_CONFIGS: dict[str, TmeVariantConfig] = {
    "experienced": TmeVariantConfig(
        variant="experienced",
        entry_url="https://join.tencentmusic.com/",
        list_path="/api/job/list",
        detail_path="/api/job/info",
        family="social",
    ),
    "campus": TmeVariantConfig(
        variant="campus",
        entry_url="https://join.tencentmusic.com/campus",
        list_path="/api/uc-job/list",
        detail_path="/api/uc-job/info",
        family="campus",
    ),
    "internship": TmeVariantConfig(
        variant="internship",
        entry_url="https://join.tencentmusic.com/campus",
        list_path="/api/uc-job/list",
        detail_path="/api/uc-job/info",
        family="campus",
    ),
}


class TmeCareerClient:
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
        self.page_size = max(1, min(50, page_size))
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
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    deduped.setdefault(
                        job_id,
                        {
                            **item,
                            "__source_site": "join.tencentmusic.com",
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
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    deduped.setdefault(
                        job_id,
                        {
                            **item,
                            "__source_site": "join.tencentmusic.com",
                        },
                    )
                    if max_items and len(deduped) >= max_items:
                        break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:max_items]

    def get_job_detail(self, *, variant: str, job_id: str) -> dict[str, Any]:
        config = VARIANT_CONFIGS[variant]
        with self._new_client(config.entry_url) as client:
            response = client.get(
                f"{TME_BASE_URL}{config.detail_path}",
                params={"id": job_id},
            )
            response.raise_for_status()
        payload = self._safe_json(response)
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def detail_url(self, *, variant: str, job_id: str) -> str:
        config = VARIANT_CONFIGS[variant]
        return f"{TME_BASE_URL}{config.detail_path}?id={quote(job_id, safe='')}"

    def _new_client(self, referer: str) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": TME_BASE_URL,
                "Referer": referer,
            },
            transport=self._transport,
            trust_env=False,
        )

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: TmeVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.post(
                f"{TME_BASE_URL}{config.list_path}",
                json={
                    "page": current,
                    "limit": self.page_size,
                    "keyword": keyword,
                },
            )
            response.raise_for_status()
            payload = self._safe_json(response)
            if str(payload.get("code") or "") not in {"200", "0"}:
                break

            data = payload.get("data") or {}
            page_items = data.get("items") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))

            meta = data.get("_meta") or {}
            page_count = self._as_int(meta.get("page_count"))
            if page_count and current >= page_count:
                break
            total_count = self._as_int(meta.get("total_count"))
            if total_count and current * self.page_size >= total_count:
                break
        return items

    def _matches_variant(self, *, variant: str, payload: dict[str, Any]) -> bool:
        if variant == "experienced":
            return True

        descriptor = str(payload.get("job_type_descr") or "").casefold()
        job_type = str(payload.get("job_type") or "").casefold()
        name = str(payload.get("name") or "").casefold()
        marker = any(token in descriptor or token in job_type or token in name for token in _INTERN_MARKERS)

        if variant == "internship":
            return marker
        return not marker

    def _normalized_keywords(self, keywords: list[str]) -> list[str]:
        query_keywords = [item.strip() for item in keywords if item and item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        return query_keywords or [""]

    def _sort_key(self, payload: dict[str, Any]) -> tuple[int, int]:
        posted_at = parse_tme_date(payload.get("date"))
        date_ts = int(posted_at.timestamp()) if posted_at else 0
        return date_ts, self._as_int(payload.get("id"))

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _as_int(self, value: Any) -> int:
        try:
            return int(str(value or "0"))
        except (TypeError, ValueError):
            return 0
