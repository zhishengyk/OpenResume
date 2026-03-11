from __future__ import annotations

from dataclasses import dataclass
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
                for item in self._collect_keyword_jobs(client, keyword=keyword):
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("jobUnionId") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(client, keyword=""):
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("jobUnionId") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def get_job_detail(
        self,
        *,
        variant: str,
        job_id: str,
    ) -> dict[str, Any]:
        config = VARIANT_CONFIGS[variant]
        with self._new_client(config.entry_url) as client:
            response = client.post(
                f"{BASE_URL}/api/official/job/getJobDetail",
                json={"jobUnionId": job_id},
            )
            response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

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
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.post(
                f"{BASE_URL}/api/official/job/getJobList",
                json=self._list_payload(current=current, keyword=keyword),
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or {}
            page_items = data.get("list") or []
            if not isinstance(page_items, list) or not page_items:
                break

            items.extend(item for item in page_items if isinstance(item, dict))
            page = data.get("page") or {}
            try:
                total_pages = int(page.get("totalPage") or 0)
            except (TypeError, ValueError):
                total_pages = 0
            if total_pages and current >= total_pages:
                break
        return items

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
