from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


BASE_URL = "https://campus.kuaishou.cn/recruit/campus/e"
DICT_TYPES = (
    "workLocation,positionCategory,positionCategoryFlatten,positionNature,recruitSubProject"
)


@dataclass(frozen=True)
class KuaishouCampusVariantConfig:
    variant: str
    position_nature_code: str


VARIANT_CONFIGS: dict[str, KuaishouCampusVariantConfig] = {
    "campus": KuaishouCampusVariantConfig(
        variant="campus",
        position_nature_code="fulltime",
    ),
    "internship": KuaishouCampusVariantConfig(
        variant="internship",
        position_nature_code="intern",
    ),
}


class KuaishouCampusClient:
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
            recruit_codes = self._resolve_recruit_sub_project_codes(
                client,
                variant=config.variant,
            )
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                    recruit_codes=recruit_codes,
                ):
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "campus.kuaishou.cn")
                    normalized.setdefault("__source_channel", "campus")
                    deduped.setdefault(job_id, normalized)

            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword="",
                    recruit_codes=recruit_codes,
                ):
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "campus.kuaishou.cn")
                    normalized.setdefault("__source_channel", "campus")
                    deduped.setdefault(job_id, normalized)

            if not deduped and recruit_codes:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword="",
                    recruit_codes=[],
                ):
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "campus.kuaishou.cn")
                    normalized.setdefault("__source_channel", "campus")
                    deduped.setdefault(job_id, normalized)

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def get_job_detail(self, *, job_id: str) -> dict[str, Any]:
        with self._new_client() as client:
            response = client.get(
                f"{BASE_URL}/api/v1/open/positions/find",
                params={"id": job_id},
            )
            response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 0:
            return {}
        detail = payload.get("result")
        return detail if isinstance(detail, dict) else {}

    def detail_url(self, *, variant: str, job_id: str, position_code: str = "") -> str:
        nature = VARIANT_CONFIGS[variant].position_nature_code
        if position_code:
            encoded_code = quote(position_code, safe="")
            return (
                "https://campus.kuaishou.cn/recruit/campus/e/#/campus/job-info/"
                f"?code={encoded_code}&positionNatureCode={nature}"
            )
        return (
            "https://campus.kuaishou.cn/recruit/campus/e/#/campus/job-info/"
            f"?id={quote(job_id, safe='')}&positionNatureCode={nature}"
        )

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://campus.kuaishou.cn",
                "Referer": "https://campus.kuaishou.cn/recruit/campus/e/",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _resolve_recruit_sub_project_codes(
        self,
        client: httpx.Client,
        *,
        variant: str,
    ) -> list[str]:
        try:
            response = client.get(
                f"{BASE_URL}/api/v1/dictionary/batch",
                params={"types": DICT_TYPES},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        if int(payload.get("code") or 0) != 0:
            return []
        result = payload.get("result") or {}
        items = result.get("recruitSubProject") or []
        if not isinstance(items, list):
            return []

        preferred_tokens = ("实习",) if variant == "internship" else ("应届", "校招")
        preferred_codes: list[str] = []
        fallback_codes: list[str] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            name = str(item.get("name") or "")
            fallback_codes.append(code)
            if any(token in name for token in preferred_tokens):
                preferred_codes.append(code)

        return preferred_codes or fallback_codes

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: KuaishouCampusVariantConfig,
        keyword: str,
        recruit_codes: list[str],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            body: dict[str, Any] = {
                "pageSize": self.page_size,
                "pageNum": current,
                "positionNatureCode": config.position_nature_code,
            }
            if recruit_codes:
                body["recruitSubProjectCodes"] = recruit_codes
            if keyword:
                body["name"] = keyword

            response = client.post(
                f"{BASE_URL}/api/v1/open/positions/simple",
                json=body,
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

    def _sort_key(self, item: dict[str, Any]) -> int:
        for key in ("updateTime", "createTime", "id"):
            try:
                return int(item.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return 0
