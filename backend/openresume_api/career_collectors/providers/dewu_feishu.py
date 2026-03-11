from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class DewuVariantConfig:
    variant: str
    base_url: str
    entry_url: str
    website_path: str
    detail_path_template: str
    portal_type: int = 6
    portal_channel: str = "saas-career"

    def detail_url(self, job_id: str) -> str:
        return self.detail_path_template.format(job_id=job_id)


VARIANT_CONFIGS: dict[str, DewuVariantConfig] = {
    "experienced": DewuVariantConfig(
        variant="experienced",
        base_url="https://poizon.jobs.feishu.cn",
        entry_url="https://poizon.jobs.feishu.cn/index",
        website_path="index",
        detail_path_template="https://poizon.jobs.feishu.cn/index/position/{job_id}/detail",
    ),
    "campus": DewuVariantConfig(
        variant="campus",
        base_url="https://campus.dewu.com",
        entry_url="https://campus.dewu.com/",
        website_path="578078",
        detail_path_template="https://campus.dewu.com/578078/position/{job_id}/detail",
    ),
    "internship": DewuVariantConfig(
        variant="internship",
        base_url="https://campus.dewu.com",
        entry_url="https://campus.dewu.com/",
        website_path="578078",
        detail_path_template="https://campus.dewu.com/578078/position/{job_id}/detail",
    ),
}


class DewuFeishuClient:
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
            csrf_token = self._fetch_csrf_token(client, config=config)
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

    def fetch_detail(
        self,
        *,
        variant: str,
        job_id: str,
    ) -> dict[str, Any]:
        config = VARIANT_CONFIGS[variant]
        with self._new_client() as client:
            csrf_token = self._fetch_csrf_token(client, config=config)
            response = client.get(
                f"{config.base_url}/api/v1/job/posts/{job_id}",
                headers=self._api_headers(config=config, csrf_token=csrf_token),
                params={
                    "portal_type": config.portal_type,
                    "source_job_post_id": job_id,
                    "with_recommend": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            detail = ((payload.get("data") or {}).get("job_post_detail")) or {}
            return detail if isinstance(detail, dict) else {}

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

    def _fetch_csrf_token(
        self,
        client: httpx.Client,
        *,
        config: DewuVariantConfig,
    ) -> str:
        response = client.post(
            f"{config.base_url}/api/v1/csrf/token",
            headers=self._api_headers(config=config, csrf_token="undefined"),
            json={"portal_entrance": 1},
        )
        response.raise_for_status()
        payload = response.json()
        return str(((payload.get("data") or {}).get("token")) or "")

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: DewuVariantConfig,
        csrf_token: str,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.post(
                f"{config.base_url}/api/v1/search/job/posts",
                headers=self._api_headers(config=config, csrf_token=csrf_token),
                json=self._search_payload(keyword, current=current, config=config),
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or {}
            page_items = data.get("job_post_list") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))
            try:
                total = int(data.get("count") or 0)
            except (TypeError, ValueError):
                total = 0
            if total and current * self.page_size >= total:
                break
        return items

    def _api_headers(
        self,
        *,
        config: DewuVariantConfig,
        csrf_token: str,
    ) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN",
            "content-type": "application/json",
            "Portal-Channel": config.portal_channel,
            "Portal-Platform": "pc",
            "referer": config.entry_url,
            "user-agent": self.user_agent,
            "website-path": config.website_path,
            "x-csrf-token": csrf_token,
        }

    def _search_payload(
        self,
        keyword: str,
        *,
        current: int,
        config: DewuVariantConfig,
    ) -> dict[str, Any]:
        return {
            "keyword": keyword,
            "limit": self.page_size,
            "offset": (current - 1) * self.page_size,
            "job_hot_flag": None,
            "job_category_id_list": [],
            "tag_id_list": [],
            "location_code_list": [],
            "subject_id_list": [],
            "recruitment_id_list": [],
            "portal_type": config.portal_type,
            "job_function_id_list": [],
            "storefront_id_list": [],
        }

    def _matches_variant(self, *, variant: str, item: dict[str, Any]) -> bool:
        recruit_type = item.get("recruit_type") or {}
        if not isinstance(recruit_type, dict):
            return variant != "internship"

        parent = recruit_type.get("parent") or {}
        if not isinstance(parent, dict):
            parent = {}

        parent_id = str(parent.get("id") or "").strip()
        child_id = str(recruit_type.get("id") or "").strip()
        parent_text = self._marker_text(
            parent.get("name"),
            parent.get("en_name"),
            parent.get("i18n_name"),
        )
        child_text = self._marker_text(
            recruit_type.get("name"),
            recruit_type.get("en_name"),
            recruit_type.get("i18n_name"),
        )
        title_text = self._marker_text(item.get("title"))

        if variant == "experienced":
            if parent_id or parent_text:
                return parent_id == "1" or "experienced" in parent_text or "社招" in parent_text
            return "intern" not in title_text and "实习" not in title_text

        if variant == "campus":
            if parent_id and parent_id != "2":
                return False
            if "experienced" in parent_text or "社招" in parent_text:
                return False
            if child_id == "202" or "intern" in child_text or "实习" in child_text:
                return False
            return parent_id == "2" or "campus" in parent_text or "校招" in parent_text

        if variant == "internship":
            if child_id:
                return child_id == "202"
            if "intern" in child_text or "实习" in child_text:
                return True
            return "intern" in title_text or "实习" in title_text

        return True

    def _marker_text(self, *values: Any) -> str:
        return " ".join(str(value or "") for value in values).casefold()

    def _sort_key(self, item: dict[str, Any]) -> int:
        try:
            return int(item.get("publish_time") or 0)
        except (TypeError, ValueError):
            return 0
