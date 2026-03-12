from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import quote

import httpx


BAIDU_BASE_URL = "https://talent.baidu.com"
_INITIAL_DATA_MARKER = "window.__INITIAL_DATA__"


def parse_baidu_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class BaiduVariantConfig:
    variant: str
    entry_url: str
    recruit_type: str


VARIANT_CONFIGS: dict[str, BaiduVariantConfig] = {
    "experienced": BaiduVariantConfig(
        variant="experienced",
        entry_url="https://talent.baidu.com/jobs/social-list",
        recruit_type="SOCIAL",
    ),
    "campus": BaiduVariantConfig(
        variant="campus",
        entry_url="https://talent.baidu.com/jobs/list?recruitType=GRADUATE",
        recruit_type="GRADUATE",
    ),
    "internship": BaiduVariantConfig(
        variant="internship",
        entry_url="https://talent.baidu.com/jobs/list?recruitType=INTERN",
        recruit_type="INTERN",
    ),
}


class BaiduJobClient:
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
        query_keywords = self._normalized_keywords(keywords)
        max_items = max(1, limit) if limit else None
        deduped: dict[str, dict[str, Any]] = {}

        with self._new_client(config.entry_url) as client:
            response = client.get(config.entry_url)
            response.raise_for_status()
        initial_data = self._extract_initial_data(response.text)
        list_data = initial_data.get("listData") or {}
        jobs = list_data.get("listDetailData") or []
        if not isinstance(jobs, list):
            jobs = []

        normalized_jobs = [
            {
                **job,
                "__source_site": "talent.baidu.com",
                "__entry_url": config.entry_url,
                "__recruit_type": config.recruit_type,
            }
            for job in jobs
            if isinstance(job, dict)
        ]

        for keyword in query_keywords:
            for item in normalized_jobs:
                job_id = self._job_id(item)
                if not job_id:
                    continue
                if keyword and not self._matches_keyword(item=item, keyword=keyword):
                    continue
                deduped.setdefault(job_id, item)
                if max_items and len(deduped) >= max_items:
                    break
            if max_items and len(deduped) >= max_items:
                break

        if not deduped and query_keywords != [""]:
            for item in normalized_jobs:
                job_id = self._job_id(item)
                if not job_id:
                    continue
                deduped.setdefault(job_id, item)
                if max_items and len(deduped) >= max_items:
                    break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:max_items]

    def detail_url(
        self,
        *,
        variant: str,
        job_id: str,
        entry_url: str = "",
    ) -> str:
        config = VARIANT_CONFIGS[variant]
        base = entry_url or config.entry_url
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}postId={quote(job_id, safe='')}"

    def _new_client(self, referer: str) -> httpx.Client:
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

    def _extract_initial_data(self, html_text: str) -> dict[str, Any]:
        raw = self._extract_initial_data_object(html_text)
        if not raw:
            return {}

        # The payload occasionally contains JS `undefined` values.
        cleaned = re.sub(r":\s*undefined\b", ": null", raw)
        try:
            payload = json.loads(cleaned)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _extract_initial_data_object(self, html_text: str) -> str:
        text = html_text or ""
        marker_index = text.find(_INITIAL_DATA_MARKER)
        if marker_index < 0:
            return ""

        assign_index = text.find("=", marker_index)
        if assign_index < 0:
            return ""
        start_index = text.find("{", assign_index)
        if start_index < 0:
            return ""

        depth = 0
        in_string = False
        escape = False
        quote_char = ""

        for index in range(start_index, len(text)):
            char = text[index]

            if in_string:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == quote_char:
                    in_string = False
                continue

            if char in {'"', "'"}:
                in_string = True
                quote_char = char
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    return text[start_index : index + 1]
        return ""

    def _job_id(self, payload: dict[str, Any]) -> str:
        for key in ("postId", "jobId", "id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return ""

    def _matches_keyword(self, *, item: dict[str, Any], keyword: str) -> bool:
        token = keyword.casefold().strip()
        if not token:
            return True
        haystack = " ".join(
            [
                str(item.get("name") or ""),
                str(item.get("postType") or ""),
                str(item.get("bgShortName") or ""),
                str(item.get("workPlace") or ""),
                str(item.get("workContent") or ""),
                str(item.get("serviceCondition") or ""),
            ]
        ).casefold()
        return token in haystack

    def _normalized_keywords(self, keywords: list[str]) -> list[str]:
        query_keywords = [item.strip() for item in keywords if item and item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        return query_keywords or [""]

    def _sort_key(self, payload: dict[str, Any]) -> tuple[int, int]:
        updated = parse_baidu_date(payload.get("updateDate"))
        published = parse_baidu_date(payload.get("publishDate"))
        ts = int((updated or published).timestamp()) if (updated or published) else 0
        return ts, self._as_int(self._job_id(payload))

    def _as_int(self, value: Any) -> int:
        try:
            return int(str(value or "0"))
        except (TypeError, ValueError):
            return 0
