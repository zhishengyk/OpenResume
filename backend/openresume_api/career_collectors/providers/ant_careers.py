from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx


BASE_URL = "https://hrcareersweb.antgroup.com"


@dataclass(frozen=True)
class AntCareerVariantConfig:
    variant: str
    entry_url: str
    search_path: str
    detail_path: str
    channel: str
    detail_url_template: str
    recruit_types: tuple[str, ...] = ()


VARIANT_CONFIGS: dict[str, AntCareerVariantConfig] = {
    "experienced": AntCareerVariantConfig(
        variant="experienced",
        entry_url="https://talent.antgroup.com/off-campus",
        search_path="/api/social/position/search",
        detail_path="/api/social/position/detail",
        channel="group_official_site",
        detail_url_template=(
            "https://talent.antgroup.com/off-campus-position?positionId={job_id}"
        ),
        recruit_types=(),
    ),
    "campus": AntCareerVariantConfig(
        variant="campus",
        entry_url="https://talent.antgroup.com/campus-full-list",
        search_path="/api/campus/position/search",
        detail_path="/api/campus/position/detail",
        channel="campus_group_official_site",
        detail_url_template="https://talent.antgroup.com/campus-position?positionId={job_id}",
        recruit_types=("campus_graduates",),
    ),
    "internship": AntCareerVariantConfig(
        variant="internship",
        entry_url="https://talent.antgroup.com/campus-full-list",
        search_path="/api/campus/position/search",
        detail_path="/api/campus/position/detail",
        channel="campus_group_official_site",
        detail_url_template="https://talent.antgroup.com/campus-position?positionId={job_id}",
        recruit_types=("campus_intern", "campus_talent_plan"),
    ),
}


class AntCareerClient:
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
        # Ant APIs currently return empty content for oversized pageSize values.
        self.page_size = max(1, min(10, page_size))
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
            self._warmup_search_conditions(client, config=config)
            for keyword in query_keywords:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword=keyword,
                ):
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    if (
                        config.variant == "internship"
                        and not self._looks_like_internship(item)
                    ):
                        continue
                    deduped.setdefault(job_id, item)
            if not deduped and query_keywords != [""]:
                for item in self._collect_keyword_jobs(
                    client,
                    config=config,
                    keyword="",
                ):
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    if (
                        config.variant == "internship"
                        and not self._looks_like_internship(item)
                    ):
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
        with self._new_client() as client:
            payload = self._post_json(
                client,
                path=config.detail_path,
                referer=config.entry_url,
                json_body={
                    "channel": config.channel,
                    "language": "zh",
                    "id": int(job_id),
                },
            )
        detail = payload.get("content")
        return detail if isinstance(detail, dict) else {}

    def detail_url(self, *, variant: str, job_id: str, position_url: str = "") -> str:
        if position_url:
            if position_url.startswith(("http://", "https://")):
                return position_url
            if position_url.startswith("/"):
                return f"https://talent.antgroup.com{position_url}"
        return VARIANT_CONFIGS[variant].detail_url_template.format(job_id=job_id)

    def parse_datetime(self, value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(UTC).replace(tzinfo=None)
        return dt

    def _new_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _warmup_search_conditions(
        self,
        client: httpx.Client,
        *,
        config: AntCareerVariantConfig,
    ) -> None:
        try:
            self._post_json(
                client,
                path="/api/searchCondition/list",
                referer=config.entry_url,
                json_body={
                    "channel": config.channel,
                    "language": "zh",
                },
            )
        except Exception:
            return

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: AntCareerVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            payload = self._post_json(
                client,
                path=config.search_path,
                referer=config.entry_url,
                json_body=self._search_payload(
                    config=config,
                    current=current,
                    keyword=keyword,
                ),
            )
            page_items = payload.get("content") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))
            try:
                total = int(payload.get("totalCount") or 0)
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
        referer: str,
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        response = client.post(
            f"{BASE_URL}{path}",
            json=json_body,
            headers={
                "Origin": "https://talent.antgroup.com",
                "Referer": referer,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _search_payload(
        self,
        *,
        config: AntCareerVariantConfig,
        current: int,
        keyword: str,
    ) -> dict[str, Any]:
        if config.variant == "experienced":
            return {
                "key": keyword,
                "regions": "",
                "categories": "",
                "subCategories": "",
                "bgCode": "",
                "socialQrCode": "",
                "pageIndex": current,
                "pageSize": self.page_size,
                "channel": config.channel,
                "language": "zh",
            }
        return {
            "channel": config.channel,
            "language": "zh",
            "searchKey": keyword,
            "regions": "",
            "subCategories": "",
            "bgCode": "",
            "pageIndex": current,
            "pageSize": self.page_size,
            "recruitType": list(config.recruit_types),
            "batchIds": [],
        }

    def _looks_like_internship(self, payload: dict[str, Any]) -> bool:
        marker = " ".join(
            str(payload.get(key) or "")
            for key in ("name", "batchName", "project", "positionType", "categoryName")
        ).lower()
        return "实习" in marker or "intern" in marker

    def _sort_key(self, item: dict[str, Any]) -> int:
        publish_time = self.parse_datetime(item.get("publishTime"))
        if publish_time is None:
            return 0
        return int(publish_time.timestamp())
