from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.parse import quote

import httpx


JOINQQ_BASE_URL = "https://join.qq.com"
MAX_EXPANDED_KEYWORDS = 12
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ROLE_KEYWORD_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("\u524d\u7aef", ("frontend engineer", "frontend developer", "frontend")),
    ("\u540e\u7aef", ("backend engineer", "backend developer", "server engineer")),
    ("\u5168\u6808", ("full stack engineer", "fullstack engineer")),
    ("\u5ba2\u6237\u7aef", ("client engineer", "ios engineer", "android engineer")),
    ("\u7b97\u6cd5", ("algorithm engineer", "machine learning engineer")),
    ("\u6570\u636e", ("data engineer", "data scientist")),
    ("\u6d4b\u8bd5", ("test engineer", "qa engineer", "sdet")),
    ("\u8fd0\u7ef4", ("devops engineer", "site reliability engineer", "sre")),
)


@dataclass(frozen=True)
class TencentJoinQQVariantConfig:
    variant: str


VARIANT_CONFIGS: dict[str, TencentJoinQQVariantConfig] = {
    "experienced": TencentJoinQQVariantConfig(variant="experienced"),
    "campus": TencentJoinQQVariantConfig(variant="campus"),
    "internship": TencentJoinQQVariantConfig(variant="internship"),
}


class TencentJoinQQClient:
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
        if config.variant == "experienced":
            # join.qq.com is campus-focused; keep experienced jobs on careers.tencent.com.
            return []

        deduped: dict[str, dict[str, Any]] = {}
        keyword_list = self._normalized_keywords(keywords)
        last_request_error: Exception | None = None

        with httpx.Client(
            timeout=self.timeout_seconds,
            headers=self._default_headers(),
            follow_redirects=True,
            transport=self._transport,
            trust_env=False,
        ) as client:
            project_mapping_ids = self._resolve_project_mapping_ids(client, variant=config.variant)
            if not project_mapping_ids:
                return []

            for keyword in keyword_list:
                try:
                    payloads = self._collect_keyword_jobs(
                        client,
                        keyword=keyword,
                        project_mapping_ids=project_mapping_ids,
                    )
                except httpx.HTTPError as error:
                    last_request_error = error
                    continue

                for item in payloads:
                    job_id = str(item.get("postId") or item.get("id") or "").strip()
                    if not job_id:
                        continue
                    normalized = dict(item)
                    normalized.setdefault("__source_site", "join.qq.com")
                    deduped.setdefault(job_id, normalized)

        if not deduped and last_request_error is not None:
            raise RuntimeError("Tencent join.qq API request failed") from last_request_error

        return sorted(deduped.values(), key=self._sort_key, reverse=True)

    def detail_url(self, *, post_id: str) -> str:
        return f"{JOINQQ_BASE_URL}/post_detail.html?postid={quote(post_id, safe='')}"

    def _resolve_project_mapping_ids(
        self,
        client: httpx.Client,
        *,
        variant: str,
    ) -> list[int]:
        payload = self._request_json(
            client,
            method="GET",
            path="/api/v1/position/getProjectMapping",
            params={"lang": "zh-cn"},
        )
        status = int(payload.get("status") or 0)
        if status != 0:
            return []

        records = payload.get("data") or []
        if not isinstance(records, list):
            return []

        ids: list[int] = []
        intern_token = "\u5b9e\u4e60"
        campus_tokens = ("\u5e94\u5c4a", "\u63d0\u524d\u6279")
        seen: set[int] = set()

        for item in records:
            if not isinstance(item, dict):
                continue
            recruit_type = self._as_int(item.get("recruitType"))
            sub_items = item.get("subProjectList") or []
            if not isinstance(sub_items, list):
                continue
            for sub in sub_items:
                if not isinstance(sub, dict):
                    continue
                mapping_id = self._as_int(sub.get("id") or sub.get("mappingId"))
                if mapping_id <= 0:
                    continue
                project_name = str(sub.get("projectName") or "")

                include = False
                if variant == "campus":
                    include = recruit_type == 1
                    if recruit_type == 999:
                        has_campus_token = any(token in project_name for token in campus_tokens)
                        include = has_campus_token and intern_token not in project_name
                elif variant == "internship":
                    include = recruit_type == 2
                    if recruit_type == 999 and intern_token in project_name:
                        include = True

                if include and mapping_id not in seen:
                    seen.add(mapping_id)
                    ids.append(mapping_id)

        return ids

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        keyword: str,
        project_mapping_ids: list[int],
    ) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for page_index in range(1, self.max_pages + 1):
            payload = self._request_json(
                client,
                method="POST",
                path="/api/v1/position/searchPosition",
                json_body=self._search_payload(
                    page_index=page_index,
                    keyword=keyword,
                    project_mapping_ids=project_mapping_ids,
                ),
            )
            status = int(payload.get("status") or 0)
            if status != 0:
                raise RuntimeError(f"Tencent join.qq API returned status={status}")
            data = payload.get("data") or {}
            page_items = data.get("positionList") or []
            if not isinstance(page_items, list) or not page_items:
                break
            jobs.extend(item for item in page_items if isinstance(item, dict))

            total_count = self._as_int(data.get("count"))
            if total_count and page_index * self.page_size >= total_count:
                break
        return jobs

    def _request_json(
        self,
        client: httpx.Client,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = client.request(
            method=method,
            url=f"{JOINQQ_BASE_URL}{path}",
            params=params,
            json=json_body,
            headers={
                "Referer": "https://join.qq.com/post.html?query=p_2",
                "Origin": "https://join.qq.com",
            },
        )
        response.raise_for_status()
        return self._decode_json(response)

    def _search_payload(
        self,
        *,
        page_index: int,
        keyword: str,
        project_mapping_ids: list[int],
    ) -> dict[str, Any]:
        return {
            "projectIdList": [],
            "projectMappingIdList": project_mapping_ids,
            "keyword": keyword.strip(),
            "bgList": [],
            "workCountryType": 0,
            "workCityList": [],
            "recruitCityList": [],
            "positionFidList": [],
            "pageIndex": page_index,
            "pageSize": self.page_size,
        }

    def _decode_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            pass
        try:
            payload = json.loads((response.content or b"").decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

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
            keyword_lower = keyword.lower()
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

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json;charset=UTF-8",
        }

    def _sort_key(self, payload: dict[str, Any]) -> tuple[int, int]:
        project_id = self._as_int(payload.get("projectId"))
        post_id = self._as_int(payload.get("postId") or payload.get("id"))
        return project_id, post_id

    def _as_int(self, value: Any) -> int:
        try:
            return int(str(value or "0"))
        except (TypeError, ValueError):
            return 0
