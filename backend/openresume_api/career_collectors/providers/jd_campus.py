from __future__ import annotations

from dataclasses import dataclass
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

        with self._new_client(referer=config.entry_url) as client:
            self._warmup(client)
            self._load_dictionary(client, config=config)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                ):
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword="",
                ):
                    job_id = self._job_id(item)
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

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

    def detail_url(self, *, variant: str, publish_id: str) -> str:
        type_code = VARIANT_CONFIGS[variant].type_code
        if publish_id:
            return f"{BASE_URL}/#/jobs?type={type_code}&publishId={publish_id}"
        return f"{BASE_URL}/#/jobs?type={type_code}"

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
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page_index in range(self.max_pages):
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
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))
            try:
                total = int(body.get("totalNumber") or 0)
            except (TypeError, ValueError):
                total = 0
            if total and (page_index + 1) * self.page_size >= total:
                break
        return items

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
