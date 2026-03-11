from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import quote

import httpx


BASE_URL = "https://zhaopin.kuaishou.cn/recruit/e"
SIGN_SECRET = "652f962a-0575-4575-98d2-f04e2291bee2"


@dataclass(frozen=True)
class KuaishouSocialVariantConfig:
    variant: str
    entry_url: str
    position_nature_code: str
    recruit_project: str


VARIANT_CONFIGS: dict[str, KuaishouSocialVariantConfig] = {
    "experienced": KuaishouSocialVariantConfig(
        variant="experienced",
        entry_url="https://zhaopin.kuaishou.cn/",
        position_nature_code="C001",
        recruit_project="socialr",
    ),
    "internship": KuaishouSocialVariantConfig(
        variant="internship",
        entry_url="https://zhaopin.kuaishou.cn/",
        position_nature_code="C002",
        recruit_project="socialr",
    ),
}


class KuaishouSocialClient:
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

        with self._new_client() as client:
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                ):
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "zhaopin.kuaishou.cn")
                    normalized.setdefault("__source_channel", "social")
                    deduped.setdefault(job_id, normalized)

            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword="",
                ):
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "zhaopin.kuaishou.cn")
                    normalized.setdefault("__source_channel", "social")
                    deduped.setdefault(job_id, normalized)

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def detail_url(self, *, job_id: str) -> str:
        return f"https://zhaopin.kuaishou.cn/recruit/e/#/official/index/job-info/{job_id}"

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://zhaopin.kuaishou.cn",
                "Referer": "https://zhaopin.kuaishou.cn/",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: KuaishouSocialVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            query: dict[str, Any] = {
                "pageNum": current,
                "pageSize": self.page_size,
                "positionNatureCode": config.position_nature_code,
                "recruitProject": config.recruit_project,
            }
            if keyword:
                query["name"] = keyword

            signed_headers = self._signed_headers(query=query, body="")
            response = client.get(
                f"{BASE_URL}/api/v1/open/positions/simple",
                params=query,
                headers=signed_headers,
            )
            response.raise_for_status()
            payload = response.json()
            if int(payload.get("code") or 0) != 0:
                break
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

    def _signed_headers(self, *, query: dict[str, Any], body: str) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        sign_source = (
            f"{timestamp}{self._canonical_query_string(query)}{body}{SIGN_SECRET}"
        )
        sign = hmac.new(
            SIGN_SECRET.encode("utf-8"),
            sign_source.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "signTimestamp": timestamp,
            "sign": sign,
        }

    def _canonical_query_string(self, query: dict[str, Any]) -> str:
        items: list[str] = []
        for key in sorted(query):
            value = query[key]
            if isinstance(value, list):
                value = ",".join(sorted(str(item) for item in value))
            encoded = quote(str(value), safe="").replace("%20", "+")
            items.append(f"{key}={encoded}")
        return "&".join(items)

    def _sort_key(self, item: dict[str, Any]) -> int:
        for key in ("updateTime", "createTime", "id"):
            try:
                return int(item.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return 0
