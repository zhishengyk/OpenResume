from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class TencentVariantConfig:
    variant: str
    attr_id: str


VARIANT_CONFIGS: dict[str, TencentVariantConfig] = {
    "experienced": TencentVariantConfig(variant="experienced", attr_id="1"),
    "campus": TencentVariantConfig(variant="campus", attr_id="2,5"),
    "internship": TencentVariantConfig(variant="internship", attr_id="3"),
}

ROLE_KEYWORD_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("前端", ("frontend engineer", "frontend developer", "frontend")),
    ("后端", ("backend engineer", "backend developer", "server engineer")),
    ("全栈", ("full stack engineer", "fullstack engineer")),
    ("客户端", ("client engineer", "ios engineer", "android engineer")),
    ("算法", ("algorithm engineer", "machine learning engineer")),
    ("数据", ("data engineer", "data scientist")),
    ("测试", ("test engineer", "qa engineer", "sdet")),
    ("运维", ("devops engineer", "site reliability engineer", "sre")),
)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
MAX_EXPANDED_KEYWORDS = 12


def parse_tencent_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    # Handles formats like "2026年03月10日" or "2026-03-10".
    match = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if not match:
        return None
    try:
        return datetime(
            year=int(match.group(1)),
            month=int(match.group(2)),
            day=int(match.group(3)),
        )
    except ValueError:
        return None


class TencentCareerClient:
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
        self.page_size = max(1, min(50, page_size))
        self._transport = transport

    def collect_jobs(
        self,
        *,
        variant: str,
        keywords: list[str],
    ) -> list[dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        keyword_list = self._normalized_keywords(keywords)
        deduped: dict[str, dict[str, Any]] = {}
        last_request_error: Exception | None = None

        with httpx.Client(
            timeout=self.timeout_seconds,
            headers=self._default_headers(),
            follow_redirects=True,
            transport=self._transport,
            trust_env=False,
        ) as client:
            for keyword in keyword_list:
                try:
                    payloads = self._collect_keyword_jobs(
                        client,
                        config=config,
                        keyword=keyword,
                    )
                except httpx.HTTPError as error:
                    last_request_error = error
                    continue

                for payload in payloads:
                    post_id = str(payload.get("PostId") or "")
                    if not post_id:
                        continue
                    deduped.setdefault(post_id, payload)

        if not deduped and last_request_error is not None:
            raise RuntimeError("Tencent Query API request failed") from last_request_error

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def detail_url(self, *, job_id: str) -> str:
        return f"http://careers.tencent.com/jobdesc.html?postId={quote(job_id, safe='')}"

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: TencentVariantConfig,
        keyword: str,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for page_index in range(1, self.max_pages + 1):
            payload = self._request_query(
                client,
                page_index=page_index,
                config=config,
                keyword=keyword,
            )
            code = int(payload.get("Code") or 0)
            if code != 200:
                raise RuntimeError(f"Tencent Query API returned code={code}")

            data = payload.get("Data") or {}
            posts = data.get("Posts") or []
            if not isinstance(posts, list) or not posts:
                break
            collected.extend(item for item in posts if isinstance(item, dict))

            total_count = self._as_int(data.get("Count"))
            if total_count and page_index * self.page_size >= total_count:
                break
        return collected

    def _request_query(
        self,
        client: httpx.Client,
        *,
        page_index: int,
        config: TencentVariantConfig,
        keyword: str,
    ) -> dict[str, Any]:
        response = client.get(
            "https://careers.tencent.com/tencentcareer/api/post/Query",
            params=self._query_params(
                page_index=page_index,
                config=config,
                keyword=keyword,
            ),
            headers={"Referer": "https://careers.tencent.com/search.html"},
        )
        response.raise_for_status()
        return self._decode_json(response)

    def _query_params(
        self,
        *,
        page_index: int,
        config: TencentVariantConfig,
        keyword: str,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageIndex": page_index,
            "pageSize": self.page_size,
            "language": "zh-cn",
            "area": "cn",
            "attrId": config.attr_id,
        }
        if keyword.strip():
            params["keyword"] = keyword.strip()
        return params

    def _decode_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            pass

        body = response.content or b""
        for encoding in ("utf-8", "gb18030"):
            try:
                text = body.decode(encoding)
                payload = json.loads(text)
                return payload if isinstance(payload, dict) else {}
            except Exception:
                continue
        raise RuntimeError("Failed to decode Tencent Query API payload")

    def _normalized_keywords(self, keywords: list[str]) -> list[str]:
        normalized = [
            item.strip()
            for item in (keywords or [])
            if isinstance(item, str) and item.strip()
        ]
        if not normalized:
            return [""]

        expanded: list[str] = []
        seen: set[str] = set()

        def push(value: str) -> None:
            normalized_value = re.sub(r"\s+", " ", str(value or "")).strip()
            if not normalized_value:
                return
            marker = normalized_value.casefold()
            if marker in seen:
                return
            seen.add(marker)
            expanded.append(normalized_value)

        for keyword in normalized:
            push(keyword)
            keyword_lower = keyword.strip().lower()
            push(keyword_lower)
            if "-" in keyword_lower:
                push(keyword_lower.replace("-", " "))
            if " " in keyword_lower:
                push(keyword_lower.replace(" ", "-"))

            if CJK_RE.search(keyword):
                for token, aliases in ROLE_KEYWORD_HINTS:
                    if token in keyword:
                        for alias in aliases:
                            push(alias)

            if len(expanded) >= MAX_EXPANDED_KEYWORDS:
                return expanded[:MAX_EXPANDED_KEYWORDS]

        return expanded[:MAX_EXPANDED_KEYWORDS] or [""]

    def _sort_key(self, payload: dict[str, Any]) -> tuple[int, int]:
        date_value = parse_tencent_date(payload.get("LastUpdateTime"))
        date_ts = int(date_value.timestamp()) if date_value is not None else 0
        post_id = self._as_int(payload.get("PostId"))
        return date_ts, post_id

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def _as_int(self, value: Any) -> int:
        try:
            return int(str(value or "0"))
        except (TypeError, ValueError):
            return 0
