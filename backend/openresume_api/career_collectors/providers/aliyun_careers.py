from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import httpx


BASE_URL = "https://careers.aliyun.com"
TOKEN_PATTERN = re.compile(r'__token__\s*:\s*"([^"]+)"')


@dataclass(frozen=True)
class AliyunVariantConfig:
    variant: str
    entry_url: str
    channel: str
    category_type: str | None
    detail_path_template: str

    def detail_url(self, job_id: str) -> str:
        return self.detail_path_template.format(job_id=job_id)


VARIANT_CONFIGS: dict[str, AliyunVariantConfig] = {
    "experienced": AliyunVariantConfig(
        variant="experienced",
        entry_url="https://careers.aliyun.com/off-campus/position-list?lang=zh",
        channel="aliyun_group_official_site",
        category_type=None,
        detail_path_template=(
            "https://careers.aliyun.com/off-campus/position-detail?positionId={job_id}"
        ),
    ),
    "campus": AliyunVariantConfig(
        variant="campus",
        entry_url=(
            "https://careers.aliyun.com/campus/position-list?campusType=freshman&lang=zh"
        ),
        channel="aliyun_campus_group_official_site",
        category_type="freshman",
        detail_path_template=(
            "https://careers.aliyun.com/campus/position-detail"
            "?positionId={job_id}&campusType=freshman"
        ),
    ),
    "internship": AliyunVariantConfig(
        variant="internship",
        entry_url=(
            "https://careers.aliyun.com/campus/position-list?campusType=internship&lang=zh"
        ),
        channel="aliyun_campus_group_official_site",
        category_type="internship",
        detail_path_template=(
            "https://careers.aliyun.com/campus/position-detail"
            "?positionId={job_id}&campusType=internship"
        ),
    ),
}


class AliyunCareersClient:
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
            token = self._prepare_token(client, config.entry_url)
            self._warmup_search_conditions(client, token=token, config=config)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    token=token,
                    config=config,
                    keyword=keyword,
                ):
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    token=token,
                    config=config,
                    keyword="",
                ):
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def detail_url(self, *, variant: str, job_id: str, position_url: str = "") -> str:
        if position_url:
            if position_url.startswith("http://") or position_url.startswith("https://"):
                return position_url
            if position_url.startswith("/"):
                return f"{BASE_URL}{position_url}"
        return VARIANT_CONFIGS[variant].detail_url(job_id)

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
            transport=self._transport,
            trust_env=False,
        )

    def _prepare_token(self, client: httpx.Client, entry_url: str) -> str:
        response = client.get(entry_url, headers={"Referer": entry_url})
        response.raise_for_status()
        return self._extract_token(response.text)

    def _extract_token(self, html: str) -> str:
        text = html or ""
        matched = TOKEN_PATTERN.search(text)
        if matched:
            token = matched.group(1).strip()
            if token:
                return token
        try:
            payload = json.loads(text)
        except Exception:
            payload = {}
        token = str(payload.get("__token__") or "").strip()
        if token:
            return token
        raise RuntimeError("Failed to extract Aliyun careers token")

    def _warmup_search_conditions(
        self,
        client: httpx.Client,
        *,
        token: str,
        config: AliyunVariantConfig,
    ) -> None:
        payload = {
            "channel": config.channel,
            "language": "zh",
        }
        if config.category_type:
            payload["categoryType"] = config.category_type
        try:
            self._post_json(
                client,
                path="/searchCondition/list",
                token=token,
                referer=config.entry_url,
                json_body=payload,
            )
        except Exception:
            # Search still works without this warmup on some deployments.
            return

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        token: str,
        config: AliyunVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = self._post_json(
                client,
                path="/position/search",
                token=token,
                referer=config.entry_url,
                json_body=self._search_payload(
                    config=config,
                    current=current,
                    keyword=keyword,
                ),
            )
            payload = response.json()
            content = payload.get("content") or {}
            page_items = content.get("datas") or []
            if not isinstance(page_items, list) or not page_items:
                break

            items.extend(item for item in page_items if isinstance(item, dict))
            try:
                total = int(content.get("totalCount") or 0)
            except (TypeError, ValueError):
                total = 0
            if total and current * self.page_size >= total:
                break
        return items

    def _post_json(
        self,
        client: httpx.Client,
        *,
        path: str,
        token: str,
        referer: str,
        json_body: dict[str, Any],
    ) -> httpx.Response:
        response = client.post(
            f"{BASE_URL}{path}",
            params={"_csrf": token},
            json=json_body,
            headers=self._api_headers(token=token, referer=referer),
        )
        response.raise_for_status()
        return response

    def _api_headers(self, *, token: str, referer: str) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": BASE_URL,
            "referer": referer,
            "user-agent": self.user_agent,
            "x-csrf-token": token,
            "x-requested-with": "XMLHttpRequest",
        }

    def _search_payload(
        self,
        *,
        config: AliyunVariantConfig,
        current: int,
        keyword: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "channel": config.channel,
            "language": "zh",
            "pageIndex": current,
            "pageSize": self.page_size,
        }
        if config.category_type:
            payload["categoryType"] = config.category_type
        if keyword:
            payload["keyword"] = keyword
        return payload

    def _sort_key(self, item: dict[str, Any]) -> int:
        for key in ("publishTime", "modifyTime"):
            try:
                return int(item.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return 0
