from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import html
import json
import re
from typing import Any
from urllib.parse import quote

import httpx


DIDI_SOCIAL_BASE_URL = "https://talent.didiglobal.com"
DIDI_CAMPUS_ENTRY_URL = "https://campus.didiglobal.com/"
_SOCIAL_LIST_PATH = "/recruit-portal-service/api/job/front/list"
_SOCIAL_DETAIL_PATH = "/recruit-portal-service/api/job/front/view"
_INIT_DATA_PATTERN = re.compile(r'id="init-data"[^>]*value="([^"]+)"', re.IGNORECASE)
_INTERN_MARKERS = ("intern", "\u5b9e\u4e60")


def parse_didi_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None

    try:
        numeric = float(text)
        if numeric > 10_000_000_000:
            return datetime.fromtimestamp(numeric / 1000, UTC).replace(tzinfo=None)
        if numeric > 1_000_000_000:
            return datetime.fromtimestamp(numeric, UTC).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class DidiVariantConfig:
    variant: str
    mode: str
    entry_url: str


VARIANT_CONFIGS: dict[str, DidiVariantConfig] = {
    "experienced": DidiVariantConfig(
        variant="experienced",
        mode="social",
        entry_url="https://talent.didiglobal.com/social/list/1",
    ),
    "campus": DidiVariantConfig(
        variant="campus",
        mode="campus",
        entry_url=DIDI_CAMPUS_ENTRY_URL,
    ),
    "internship": DidiVariantConfig(
        variant="internship",
        mode="campus",
        entry_url=DIDI_CAMPUS_ENTRY_URL,
    ),
}


class DidiCareerClient:
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
        max_items = max(1, limit) if limit else None
        if config.mode == "social":
            items = self._collect_social_jobs(keywords=keywords, limit=max_items)
        else:
            items = self._collect_campus_jobs(
                variant=variant,
                keywords=keywords,
                limit=max_items,
            )
        return items[:max_items]

    def get_social_job_detail(self, *, job_id: str) -> dict[str, Any]:
        with self._new_social_client() as client:
            response = client.get(f"{DIDI_SOCIAL_BASE_URL}{_SOCIAL_DETAIL_PATH}/{job_id}")
            response.raise_for_status()
            payload = self._safe_json(response)
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def social_detail_url(self, *, job_id: str) -> str:
        return f"{DIDI_SOCIAL_BASE_URL}/social/p/{quote(job_id, safe='')}"

    def campus_apply_url(self, payload: dict[str, Any] | None = None) -> str:
        if isinstance(payload, dict):
            direct = str(payload.get("__campus_apply_url") or "").strip()
            if direct:
                return direct
        return "https://campus.didiglobal.com/campus_apply/didiglobal/96064"

    def _collect_social_jobs(
        self,
        *,
        keywords: list[str],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        query_keywords = self._normalized_keywords(keywords)

        with self._new_social_client() as client:
            for keyword in query_keywords:
                for item in self._collect_social_keyword_jobs(client, keyword=keyword):
                    job_id = self._social_job_id(item)
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "talent.didiglobal.com")
                    deduped.setdefault(job_id, normalized)
                    if limit and len(deduped) >= limit:
                        break
                if limit and len(deduped) >= limit:
                    break

            if not deduped and query_keywords != [""]:
                for item in self._collect_social_keyword_jobs(client, keyword=""):
                    job_id = self._social_job_id(item)
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "talent.didiglobal.com")
                    deduped.setdefault(job_id, normalized)
                    if limit and len(deduped) >= limit:
                        break

        return sorted(deduped.values(), key=self._social_sort_key, reverse=True)

    def _collect_social_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.get(
                f"{DIDI_SOCIAL_BASE_URL}{_SOCIAL_LIST_PATH}",
                params={
                    "pageNo": current,
                    "pageSize": self.page_size,
                    "recruitType": "1",
                    "searchText": keyword,
                    "cityCode": "",
                    "positionCode": "",
                    "deptCode": "",
                    "projectCode": "",
                },
            )
            response.raise_for_status()
            payload = self._safe_json(response)
            data = payload.get("data") or {}
            page_items = data.get("items") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))

            total = self._as_int(data.get("total"))
            if total and current * self.page_size >= total:
                break
        return items

    def _collect_campus_jobs(
        self,
        *,
        variant: str,
        keywords: list[str],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        query_keywords = self._normalized_keywords(keywords)
        deduped: dict[str, dict[str, Any]] = {}

        with self._new_campus_client(config.entry_url) as client:
            response = client.get(config.entry_url)
            response.raise_for_status()
            payload = self._extract_campus_init_data(response.text)
            jobs = payload.get("jobs") or []
            if not isinstance(jobs, list):
                jobs = []

        base_apply_url = self._campus_apply_url_from_payload(payload)
        normalized_jobs = [
            {
                **item,
                "__source_site": "campus.didiglobal.com",
                "__campus_apply_url": base_apply_url,
            }
            for item in jobs
            if isinstance(item, dict)
        ]

        for keyword in query_keywords:
            for item in normalized_jobs:
                job_id = self._social_job_id(item)
                if not job_id:
                    continue
                if not self._matches_campus_variant(variant=variant, item=item):
                    continue
                if keyword and not self._campus_matches_keyword(item=item, keyword=keyword):
                    continue
                deduped.setdefault(job_id, item)
                if limit and len(deduped) >= limit:
                    break
            if limit and len(deduped) >= limit:
                break

        if not deduped and query_keywords != [""]:
            for item in normalized_jobs:
                job_id = self._social_job_id(item)
                if not job_id:
                    continue
                if not self._matches_campus_variant(variant=variant, item=item):
                    continue
                deduped.setdefault(job_id, item)
                if limit and len(deduped) >= limit:
                    break

        return sorted(deduped.values(), key=self._campus_sort_key, reverse=True)

    def _new_social_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://talent.didiglobal.com/social/list/1",
                "Origin": DIDI_SOCIAL_BASE_URL,
            },
            transport=self._transport,
            trust_env=False,
        )

    def _new_campus_client(self, referer: str) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": referer,
            },
            transport=self._transport,
            trust_env=False,
        )

    def _extract_campus_init_data(self, html_text: str) -> dict[str, Any]:
        matched = _INIT_DATA_PATTERN.search(html_text or "")
        if not matched:
            return {}
        encoded = matched.group(1)
        try:
            return json.loads(html.unescape(encoded))
        except Exception:
            return {}

    def _campus_apply_url_from_payload(self, payload: dict[str, Any]) -> str:
        org = payload.get("org") or {}
        org_id = str(org.get("id") or "").strip()
        site_id = payload.get("siteId") or org.get("siteId")
        if org_id and site_id not in (None, ""):
            return (
                "https://campus.didiglobal.com/campus_apply/"
                f"{quote(org_id, safe='')}/{quote(str(site_id), safe='')}"
            )
        return self.campus_apply_url()

    def _normalized_keywords(self, keywords: list[str]) -> list[str]:
        query_keywords = [item.strip() for item in keywords if item and item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        return query_keywords or [""]

    def _social_job_id(self, item: dict[str, Any]) -> str:
        for key in ("jdId", "recordId", "id"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return ""

    def _matches_campus_variant(self, *, variant: str, item: dict[str, Any]) -> bool:
        title = str(item.get("title") or item.get("jobName") or "").casefold()
        commitment = str(item.get("commitment") or "").casefold()
        marker = any(token in title or token in commitment for token in _INTERN_MARKERS)
        if variant == "internship":
            return marker
        if variant == "campus":
            return not marker
        return True

    def _campus_matches_keyword(self, *, item: dict[str, Any], keyword: str) -> bool:
        token = keyword.casefold().strip()
        if not token:
            return True

        text_parts: list[str] = [
            str(item.get("title") or ""),
            str(item.get("mjCode") or ""),
            str((item.get("department") or {}).get("name") or ""),
            str((item.get("zhineng") or {}).get("name") or ""),
        ]

        locations = item.get("locations") or []
        if isinstance(locations, list):
            for location in locations:
                if not isinstance(location, dict):
                    continue
                text_parts.append(str(location.get("address") or ""))
                text_parts.append(str(location.get("cityId") or ""))

        haystack = " ".join(text_parts).casefold()
        return token in haystack

    def _social_sort_key(self, item: dict[str, Any]) -> tuple[int, int]:
        posted_at = (
            parse_didi_datetime(item.get("refreshTime"))
            or parse_didi_datetime(item.get("createTime"))
            or parse_didi_datetime(item.get("analyzeTime"))
        )
        ts = int(posted_at.timestamp()) if posted_at else 0
        return ts, self._as_int(self._social_job_id(item))

    def _campus_sort_key(self, item: dict[str, Any]) -> tuple[int, int]:
        posted_at = (
            parse_didi_datetime(item.get("publishedAt"))
            or parse_didi_datetime(item.get("updatedAt"))
            or parse_didi_datetime(item.get("createdAt"))
        )
        ts = int(posted_at.timestamp()) if posted_at else 0
        return ts, self._as_int(self._social_job_id(item))

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _as_int(self, value: Any) -> int:
        try:
            return int(str(value or "0"))
        except (TypeError, ValueError):
            return 0
