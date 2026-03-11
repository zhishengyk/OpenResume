from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

import httpx


BASE_URL = "https://jobs.bilibili.com"


@dataclass(frozen=True)
class BilibiliVariantConfig:
    variant: str
    entry_url: str
    channel: str
    list_path: str
    detail_path_template: str
    recruit_type: int

    def detail_url(self, job_id: str) -> str:
        return self.detail_path_template.format(job_id=job_id)


VARIANT_CONFIGS: dict[str, BilibiliVariantConfig] = {
    "experienced": BilibiliVariantConfig(
        variant="experienced",
        entry_url="https://jobs.bilibili.com/",
        channel="social",
        list_path="/api/srs/position/positionList",
        detail_path_template="https://jobs.bilibili.com/social/positions/{job_id}",
        recruit_type=0,
    ),
    "campus": BilibiliVariantConfig(
        variant="campus",
        entry_url="https://jobs.bilibili.com/campus/",
        channel="campus",
        list_path="/api/campus/position/positionList",
        detail_path_template="https://jobs.bilibili.com/campus/positions/{job_id}",
        recruit_type=1,
    ),
    "internship": BilibiliVariantConfig(
        variant="internship",
        entry_url="https://jobs.bilibili.com/campus/",
        channel="campus",
        list_path="/api/campus/position/positionList",
        detail_path_template="https://jobs.bilibili.com/campus/positions/{job_id}",
        recruit_type=0,
    ),
}


class BilibiliClient:
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
            csrf_token = self._fetch_csrf_token(client, channel=config.channel)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    csrf_token=csrf_token,
                    keyword=keyword,
                ):
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("id") or "")
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
                    csrf_token=csrf_token,
                    keyword="",
                ):
                    if not self._matches_variant(variant=config.variant, item=item):
                        continue
                    job_id = str(item.get("id") or "")
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
            headers={"User-Agent": self.user_agent},
            transport=self._transport,
            trust_env=False,
        )

    def _fetch_csrf_token(self, client: httpx.Client, *, channel: str) -> str:
        response = client.get(
            f"{BASE_URL}/api/auth/v1/csrf/token",
            headers=self._base_headers(channel=channel),
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("data") or "")

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: BilibiliVariantConfig,
        csrf_token: str,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.post(
                f"{BASE_URL}{config.list_path}",
                headers=self._api_headers(channel=config.channel, csrf_token=csrf_token),
                json=self._list_payload(current=current, keyword=keyword, config=config),
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or {}
            page_items = data.get("list") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))
            if len(page_items) < self.page_size:
                break
        return items

    def _base_headers(self, *, channel: str) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "X-AppKey": "ops.ehr-api.auth",
            "X-UserType": "2",
            "X-Channel": channel,
        }

    def _api_headers(self, *, channel: str, csrf_token: str) -> dict[str, str]:
        headers = self._base_headers(channel=channel)
        headers["Content-Type"] = "application/json"
        headers["X-CSRF"] = csrf_token
        return headers

    def _list_payload(
        self,
        *,
        current: int,
        keyword: str,
        config: BilibiliVariantConfig,
    ) -> dict[str, Any]:
        return {
            "pageSize": self.page_size,
            "pageNum": current,
            "positionName": keyword,
            "postCode": "",
            "postCodeList": "",
            "workLocationList": "",
            "workTypeList": [],
            "positionTypeList": [],
            "deptCodeList": "",
            "recruitType": config.recruit_type,
            "practiceTypes": "",
            "onlyHotRecruit": 0,
            "ajSessionId": str(uuid.uuid4()),
        }

    def _matches_variant(self, *, variant: str, item: dict[str, Any]) -> bool:
        position_type = str(item.get("positionTypeName") or "").strip()
        title_text = str(item.get("positionName") or "").casefold()
        if variant == "experienced":
            return "intern" not in title_text and "实习" not in title_text
        if variant == "campus":
            return position_type != "实习"
        if variant == "internship":
            return position_type == "实习" or "intern" in title_text or "实习" in title_text
        return True

    def _sort_key(self, item: dict[str, Any]) -> str:
        return str(item.get("pushTime") or "")
