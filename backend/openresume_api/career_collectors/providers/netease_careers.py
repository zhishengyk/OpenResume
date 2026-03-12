from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx


NETEASE_HR_BASE_URL = "https://hr.163.com"
NETEASE_CAMPUS_BASE_URL = "https://campus.163.com"
_DEFAULT_CAMPUS_PROJECT_ID = 69


@dataclass(frozen=True)
class NeteaseVariantConfig:
    variant: str
    mode: str
    entry_url: str
    work_type: str | None = None


VARIANT_CONFIGS: dict[str, NeteaseVariantConfig] = {
    "experienced": NeteaseVariantConfig(
        variant="experienced",
        mode="hr163",
        entry_url="https://hr.163.com/",
        work_type="0",
    ),
    "campus": NeteaseVariantConfig(
        variant="campus",
        mode="campus",
        entry_url=f"https://campus.163.com/app/job/position?id={_DEFAULT_CAMPUS_PROJECT_ID}",
    ),
    "internship": NeteaseVariantConfig(
        variant="internship",
        mode="hr163",
        entry_url="https://hr.163.com/",
        work_type="1",
    ),
}


class NeteaseCareerClient:
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
        if config.mode == "hr163":
            return self._collect_hr163_jobs(
                config=config,
                keywords=keywords,
                limit=max_items,
            )
        return self._collect_campus_jobs(keywords=keywords, limit=max_items)

    def detail_url(
        self,
        *,
        variant: str,
        job_id: str,
        bee_url: str = "",
        project_id: int | str | None = None,
    ) -> str:
        if bee_url:
            if bee_url.startswith("http://") or bee_url.startswith("https://"):
                return bee_url
            if bee_url.startswith("/"):
                return f"{NETEASE_HR_BASE_URL}{bee_url}"

        if variant == "campus":
            project = self._as_int(project_id) or _DEFAULT_CAMPUS_PROJECT_ID
            return f"{NETEASE_CAMPUS_BASE_URL}/app/job/position?id={project}"

        if job_id:
            return f"{NETEASE_HR_BASE_URL}/#/position?jobId={quote(job_id, safe='')}"
        return NETEASE_HR_BASE_URL

    def _collect_hr163_jobs(
        self,
        *,
        config: NeteaseVariantConfig,
        keywords: list[str],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        query_keywords = self._normalized_keywords(keywords)

        with self._new_hr_client(config.entry_url) as client:
            for keyword in query_keywords:
                for item in self._collect_hr163_keyword_jobs(
                    client,
                    work_type=str(config.work_type or "0"),
                    keyword=keyword,
                ):
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    deduped.setdefault(
                        job_id,
                        {
                            **item,
                            "__source_site": "hr.163.com",
                        },
                    )
                    if limit and len(deduped) >= limit:
                        break
                if limit and len(deduped) >= limit:
                    break

            if not deduped and query_keywords != [""]:
                for item in self._collect_hr163_keyword_jobs(
                    client,
                    work_type=str(config.work_type or "0"),
                    keyword="",
                ):
                    job_id = str(item.get("id") or "").strip()
                    if not job_id:
                        continue
                    deduped.setdefault(
                        job_id,
                        {
                            **item,
                            "__source_site": "hr.163.com",
                        },
                    )
                    if limit and len(deduped) >= limit:
                        break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:limit]

    def _collect_hr163_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        work_type: str,
        keyword: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.post(
                f"{NETEASE_HR_BASE_URL}/api/hr163/position/queryPage",
                json={
                    "currentPage": current,
                    "pageSize": self.page_size,
                    "keyword": keyword,
                    "workType": work_type,
                },
            )
            response.raise_for_status()
            payload = self._safe_json(response)
            if self._as_int(payload.get("code")) != 200:
                break

            data = payload.get("data") or {}
            page_items = data.get("list") or []
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
        keywords: list[str],
        limit: int | None,
    ) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        query_keywords = self._normalized_keywords(keywords)

        with self._new_campus_client() as client:
            project_id = self._resolve_campus_project_id(client)
            all_jobs = self._collect_campus_project_jobs(client, project_id=project_id)

        for keyword in query_keywords:
            for item in all_jobs:
                job_id = str(item.get("id") or "").strip()
                if not job_id:
                    continue
                if keyword and not self._campus_matches_keyword(item=item, keyword=keyword):
                    continue
                deduped.setdefault(
                    job_id,
                    {
                        **item,
                        "__source_site": "campus.163.com",
                        "__project_id": project_id,
                    },
                )
                if limit and len(deduped) >= limit:
                    break
            if limit and len(deduped) >= limit:
                break

        if not deduped and query_keywords != [""]:
            for item in all_jobs:
                job_id = str(item.get("id") or "").strip()
                if not job_id:
                    continue
                deduped.setdefault(
                    job_id,
                    {
                        **item,
                        "__source_site": "campus.163.com",
                        "__project_id": project_id,
                    },
                )
                if limit and len(deduped) >= limit:
                    break

        return sorted(deduped.values(), key=self._sort_key, reverse=True)[:limit]

    def _collect_campus_project_jobs(
        self,
        client: httpx.Client,
        *,
        project_id: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for current in range(1, self.max_pages + 1):
            response = client.get(
                f"{NETEASE_CAMPUS_BASE_URL}/api/campuspc/position/getJobList",
                params={
                    "currentPage": current,
                    "pageSize": self.page_size,
                    "projectId": project_id,
                },
            )
            response.raise_for_status()
            payload = self._safe_json(response)
            if self._as_int(payload.get("code")) != 200:
                break

            data = payload.get("data") or {}
            page_items = data.get("list") or []
            if not isinstance(page_items, list) or not page_items:
                break
            items.extend(item for item in page_items if isinstance(item, dict))

            total = self._as_int(data.get("total"))
            if total and current * self.page_size >= total:
                break
        return items

    def _resolve_campus_project_id(self, client: httpx.Client) -> int:
        response = client.get(f"{NETEASE_CAMPUS_BASE_URL}/api/campuspc/project/navigation/list")
        response.raise_for_status()
        payload = self._safe_json(response)
        items = payload.get("data") or []
        if not isinstance(items, list):
            return _DEFAULT_CAMPUS_PROJECT_ID

        fallback: int | None = None
        for title, link in self._walk_nav_links(items):
            project_id = self._parse_project_id(link)
            if project_id <= 0:
                continue
            if fallback is None:
                fallback = project_id

            lowered = title.casefold()
            if "\u5e94\u5c4a" in title or "\u6821\u62db" in title or "graduate" in lowered:
                return project_id
        return fallback or _DEFAULT_CAMPUS_PROJECT_ID

    def _walk_nav_links(self, values: list[dict[str, Any]]) -> list[tuple[str, str]]:
        collected: list[tuple[str, str]] = []

        def walk(node: dict[str, Any]) -> None:
            title = str(node.get("title") or "")
            link = str(node.get("link") or "")
            if title or link:
                collected.append((title, link))
            children = node.get("children") or []
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        walk(child)

        for item in values:
            if isinstance(item, dict):
                walk(item)
        return collected

    def _parse_project_id(self, link: str) -> int:
        if not link:
            return 0
        parsed = urlparse(link)
        params = parse_qs(parsed.query or "")
        raw = (params.get("id") or [""])[0]
        return self._as_int(raw)

    def _campus_matches_keyword(self, *, item: dict[str, Any], keyword: str) -> bool:
        token = keyword.casefold().strip()
        if not token:
            return True
        haystack = " ".join(
            [
                str(item.get("positionName") or ""),
                str(item.get("positionTypeName") or ""),
                str(item.get("workPlaceName") or ""),
                str(item.get("positionDescription") or ""),
                str(item.get("positionRequirement") or ""),
            ]
        ).casefold()
        return token in haystack

    def _normalized_keywords(self, keywords: list[str]) -> list[str]:
        query_keywords = [item.strip() for item in keywords if item and item.strip()]
        query_keywords = list(dict.fromkeys(query_keywords))
        return query_keywords or [""]

    def _new_hr_client(self, referer: str) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": NETEASE_HR_BASE_URL,
                "Referer": referer,
            },
            transport=self._transport,
            trust_env=False,
        )

    def _new_campus_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{NETEASE_CAMPUS_BASE_URL}/",
            },
            transport=self._transport,
            trust_env=False,
        )

    def _sort_key(self, payload: dict[str, Any]) -> tuple[int, int]:
        updated = self._as_int(payload.get("updateTime"))
        if updated > 10_000_000_000:
            updated = updated // 1000
        if updated <= 0:
            date_str = str(payload.get("publishDate") or "").strip()
            if date_str:
                try:
                    updated = int(datetime.strptime(date_str, "%Y-%m-%d").timestamp())
                except ValueError:
                    updated = 0
        return updated, self._as_int(payload.get("id"))

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _as_int(self, value: Any) -> int:
        try:
            return int(str(value or "0"))
        except (TypeError, ValueError):
            return 0
