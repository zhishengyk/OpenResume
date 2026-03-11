from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


BASE_URL = "https://job.xiaohongshu.com"


@dataclass(frozen=True)
class XiaohongshuVariantConfig:
    variant: str
    entry_url: str
    recruit_type: str
    detail_path_template: str

    def detail_url(self, job_id: str) -> str:
        return self.detail_path_template.format(job_id=job_id)


VARIANT_CONFIGS: dict[str, XiaohongshuVariantConfig] = {
    "experienced": XiaohongshuVariantConfig(
        variant="experienced",
        entry_url="https://job.xiaohongshu.com/",
        recruit_type="social",
        detail_path_template="https://job.xiaohongshu.com/social/position/{job_id}",
    ),
    "campus": XiaohongshuVariantConfig(
        variant="campus",
        entry_url="https://job.xiaohongshu.com/campus",
        recruit_type="campus",
        detail_path_template="https://job.xiaohongshu.com/campus/position/{job_id}",
    ),
    "internship": XiaohongshuVariantConfig(
        variant="internship",
        entry_url="https://job.xiaohongshu.com/campus",
        recruit_type="intern",
        detail_path_template="https://job.xiaohongshu.com/campus/position/{job_id}",
    ),
}


class XiaohongshuClient:
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
        deduped: dict[str, dict[str, Any]] = {}
        max_items = max(1, limit) if limit else None
        query_keywords = list(dict.fromkeys(item.strip() for item in keywords if item.strip()))
        if not query_keywords:
            query_keywords = [""]

        with self._new_client() as client:
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                ):
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("positionId") or "")
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
                ):
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("positionId") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
                    if max_items and len(deduped) >= max_items:
                        break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:max_items]

    def detail_url(self, *, variant: str, job_id: str) -> str:
        return VARIANT_CONFIGS[variant].detail_url(job_id)

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/json",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: XiaohongshuVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            payload = {
                "pageNum": current,
                "pageSize": self.page_size,
                "recruitType": config.recruit_type,
            }
            if keyword:
                payload["positionName"] = keyword
            response = client.post(
                f"{BASE_URL}/websiterecruit/position/pageQueryPosition",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            data = body.get("data") or {}
            page_items = data.get("list") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))
            try:
                total = int(data.get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            if total and current * self.page_size >= total:
                break
        return items

    def _matches_variant(self, *, variant: str, item: dict[str, Any]) -> bool:
        title_text = str(item.get("positionName") or "").casefold()
        if variant == "experienced":
            return "intern" not in title_text and "实习" not in title_text
        if variant == "campus":
            return "intern" not in title_text and "实习" not in title_text
        if variant == "internship":
            return "intern" in title_text or "实习" in title_text
        return True

    def _sort_key(self, item: dict[str, Any]) -> str:
        return str(item.get("publishTime") or "")
