from __future__ import annotations

import asyncio
import json
import random
import re
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from ...services.official_sources import OfficialSource
from .base import FetchPage, OfficialExtractor
from .common import (
    build_detail_extraction,
    candidate_detail_key,
    merge_candidates,
    normalize_whitespace,
)
from .feishu import FeishuExtractor
from .generic import GenericExtractor
from .json_ssr import JsonSsrExtractor
from .site_helpers import (
    anchor_urls,
    build_candidate_from_payload,
    bundle_pages,
    first_nested_string,
    json_payloads_from_page,
    payload_detail_extraction,
    response_to_page,
    safe_fetch_page,
    script_src_urls,
    text_urls,
    unbundle_pages,
)


@dataclass
class _BytedanceApiSession:
    cookie_values: dict[str, str]
    csrf_token: str | None = None


class BytedanceExtractor(OfficialExtractor):
    name = "bytedance"

    _feishu = FeishuExtractor()
    _json = JsonSsrExtractor()
    _generic = GenericExtractor()
    _sign_helper_path = Path(__file__).with_name("bytedance_sign.cjs")
    _sign_module_cache: dict[str, str] = {}
    _user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        lowered = f"{source.url} {page.final_url} {page.text[:6000]}".lower()
        return "jobs.bytedance.com" in lowered

    async def prepare_source_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        page: FetchPage,
    ) -> FetchPage:
        pages = [page]
        allowed_hosts = {"jobs.bytedance.com"}
        visited = {
            candidate
            for candidate in [
                page.final_url,
                page.requested_url,
            ]
            if candidate
        }
        queue = [
            url
            for url in [
                "https://jobs.bytedance.com/campus",
                "https://jobs.bytedance.com/campus/position",
            ]
            if url not in visited
        ]
        for discovered_url in self._secondary_urls(page, allowed_hosts):
            if discovered_url not in visited and discovered_url not in queue:
                queue.append(discovered_url)

        while queue and len(pages) < 6:
            next_url = queue.pop(0)
            if next_url in visited:
                continue
            visited.add(next_url)
            fetched = await safe_fetch_page(client, next_url)
            if fetched is None:
                continue
            pages.append(fetched)
            if "/detail" in fetched.final_url.lower():
                continue
            for nested in self._secondary_urls(fetched, allowed_hosts):
                if nested not in visited and nested not in queue:
                    queue.append(nested)

        api_pages: list[FetchPage] = []
        position_pages = [item for item in pages if self._is_campus_position_page(item)]
        position_pages.sort(key=lambda item: self._position_page_priority(item.final_url))
        for bundled_page in position_pages:
            api_pages = await self._api_position_pages(client, bundled_page)
            if api_pages:
                break

        return bundle_pages(page, pages[1:] + api_pages, {"site": self.name})

    async def prepare_detail_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        candidate,
        page: FetchPage,
    ) -> FetchPage:
        position_id = str(candidate.raw_payload.get("position_id") or "")
        if not position_id:
            return page
        module_source = await self._load_sign_module_source(client, page)
        if not module_source:
            return page
        session = self._new_api_session()
        response = await self._request_api(
            client,
            session=session,
            module_source=module_source,
            referer_url=page.final_url or candidate.detail_url,
            method="GET",
            base_path=f"/api/v1/job/posts/{position_id}",
            params={
                "portal_type": 3,
                "source_job_post_id": position_id,
                "with_recommend": False,
            },
        )
        if response is None or response.status_code != 200:
            return page
        api_page = response_to_page(page.requested_url or candidate.detail_url, response)
        return bundle_pages(
            page,
            [
                FetchPage(
                    requested_url=api_page.final_url or page.requested_url or candidate.detail_url,
                    final_url=page.final_url or candidate.detail_url,
                    text=api_page.text,
                    status_code=api_page.status_code,
                    content_type=api_page.content_type,
                )
            ],
            {"site": self.name, "api_source": "bytedance-api"},
        )

    def _secondary_urls(self, page: FetchPage, allowed_hosts: set[str]) -> list[str]:
        urls = anchor_urls(
            page,
            allowed_hosts=allowed_hosts,
            include_keywords=("campus", "position", "page-", "detail"),
        )
        urls.extend(
            text_urls(
                page.text,
                base_url=page.final_url,
                allowed_hosts=allowed_hosts,
                include_keywords=("campus", "position", "page-", "detail"),
            )
        )
        for pattern in [
            re.compile(r"/campus(?:/position(?:\?[^\"'\s<>]+)?)?", re.I),
            re.compile(r"/campus/page-[A-Za-z0-9_-]+(?:\?[^\"'\s<>]+)?", re.I),
            re.compile(r"/campus/position/\d+/detail(?:\?[^\"'\s<>]+)?", re.I),
            re.compile(r"/campus/m/position/detail/\d+(?:\?[^\"'\s<>]+)?", re.I),
        ]:
            urls.extend(
                text_urls(
                    " ".join(match.group(0) for match in pattern.finditer(page.text)),
                    base_url=page.final_url,
                    allowed_hosts=allowed_hosts,
                )
            )
        return list(dict.fromkeys(urls))

    def extract_candidates(
        self,
        source: OfficialSource,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ):
        pages, _ = unbundle_pages(page)
        candidates = []
        for bundled_page in pages:
            candidates.extend(self._api_candidates(bundled_page, requested_cities))
            if "/detail" in bundled_page.final_url.lower():
                continue
            candidates.extend(
                self._feishu.extract_candidates(
                    source=source,
                    page=bundled_page,
                    requested_targets=requested_targets,
                    requested_cities=requested_cities,
                )
            )
            candidates.extend(
                self._json.extract_candidates(
                    source=source,
                    page=bundled_page,
                    requested_targets=requested_targets,
                    requested_cities=requested_cities,
                )
            )
            candidates.extend(
                self._generic.extract_candidates(
                    source=source,
                    page=bundled_page,
                    requested_targets=requested_targets,
                    requested_cities=requested_cities,
                )
            )
        deduped = {}
        for candidate in candidates:
            candidate.raw_payload.setdefault("site_page", candidate.company_url or page.final_url)
            candidate.raw_payload["extractor"] = self.name
            key = candidate_detail_key(candidate)
            existing = deduped.get(key)
            deduped[key] = merge_candidates(existing, candidate) if existing else candidate
        return list(deduped.values())

    def extract_detail(
        self,
        source: OfficialSource,
        candidate,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ):
        pages, _ = unbundle_pages(page)
        for bundled_page in pages:
            for payload in json_payloads_from_page(bundled_page):
                detail_payload = ((payload or {}).get("data") or {}).get("job_post_detail")
                if not isinstance(detail_payload, dict):
                    continue
                detail = payload_detail_extraction(
                    candidate=candidate,
                    page=bundled_page,
                    payload=detail_payload,
                    requested_cities=requested_cities,
                    responsibilities_keys=("description",),
                    requirements_keys=("requirement",),
                    location_keys=("city_info",),
                    department_keys=("department_info", "job_category", "job_function", "job_subject"),
                    title_keys=("title",),
                )
                if detail is None:
                    continue
                detail.section_payload["source"] = "bytedance-api"
                return detail
        best_page = max(pages, key=lambda item: len(normalize_whitespace(item.text)))
        return build_detail_extraction(candidate, best_page, requested_targets, requested_cities)

    def _api_candidates(self, page: FetchPage, requested_cities: list[str]):
        candidates = []
        for payload in json_payloads_from_page(page):
            job_post_list = ((payload or {}).get("data") or {}).get("job_post_list")
            if not isinstance(job_post_list, list):
                continue
            for item in job_post_list:
                if not isinstance(item, dict):
                    continue
                position_id = str(item.get("id") or "")
                if not position_id:
                    continue
                candidate = build_candidate_from_payload(
                    title=str(item.get("title") or ""),
                    detail_url=f"https://jobs.bytedance.com/campus/position/{position_id}/detail",
                    company_url="https://jobs.bytedance.com/campus/position",
                    requested_cities=requested_cities,
                    source_name="script-json",
                    payload=item,
                    description=str(item.get("description") or ""),
                    city_text=first_nested_string(item, ("city_info",)),
                    department=first_nested_string(
                        item,
                        ("department_info", "job_category", "job_function", "job_subject"),
                    ),
                )
                if candidate is None:
                    continue
                candidate.raw_payload["position_id"] = position_id
                candidate.raw_payload["api_source"] = "bytedance-api"
                candidates.append(candidate)
        return candidates

    def _is_campus_position_page(self, page: FetchPage) -> bool:
        parsed = urlparse(page.final_url)
        return parsed.netloc.lower() == "jobs.bytedance.com" and parsed.path == "/campus/position"

    def _position_page_priority(self, url: str) -> tuple[int, int, str]:
        parsed = urlparse(url)
        params = httpx.QueryParams(parsed.query)
        has_keyword = bool(params.get("keywords"))
        has_filters = bool(parsed.query)
        return (1 if has_keyword else 0, 1 if has_filters else 0, url)

    async def _api_position_pages(
        self,
        client: httpx.AsyncClient,
        page: FetchPage,
    ) -> list[FetchPage]:
        module_source = await self._load_sign_module_source(client, page)
        if not module_source:
            return []
        session = self._new_api_session()
        initial_state = self._search_state(page.final_url, current_override=1)
        first_response = await self._request_api(
            client,
            session=session,
            module_source=module_source,
            referer_url=page.final_url,
            method="POST",
            base_path="/api/v1/search/job/posts",
            json_body=initial_state,
        )
        if first_response is None or first_response.status_code != 200:
            return []

        try:
            first_payload = first_response.json()
        except Exception:
            return []

        job_post_list = ((first_payload.get("data") or {}).get("job_post_list")) or []
        if not isinstance(job_post_list, list) or not job_post_list:
            return []

        pages = [response_to_page(page.final_url, first_response)]
        total = 0
        try:
            total = int(((first_payload.get("data") or {}).get("count")) or 0)
        except Exception:
            total = 0
        limit = int(initial_state.get("limit") or 10)
        max_pages = min(2, max(1, (total + max(limit, 1) - 1) // max(limit, 1)))
        for current in range(2, max_pages + 1):
            response = await self._request_api(
                client,
                session=session,
                module_source=module_source,
                referer_url=page.final_url,
                method="POST",
                base_path="/api/v1/search/job/posts",
                json_body=self._search_state(page.final_url, current_override=current, limit_override=limit),
            )
            if response is None or response.status_code != 200:
                break
            pages.append(response_to_page(page.final_url, response))
        return pages

    async def _load_sign_module_source(
        self,
        client: httpx.AsyncClient,
        page: FetchPage,
    ) -> str:
        chunk_url = self._sign_chunk_url(page)
        if not chunk_url:
            return ""
        cached = self._sign_module_cache.get(chunk_url)
        if cached:
            return cached
        fetched = await safe_fetch_page(client, chunk_url)
        if fetched is None:
            return ""
        module_source = self._extract_module_function(fetched.text, 57195)
        if module_source:
            self._sign_module_cache[chunk_url] = module_source
        return module_source

    def _sign_chunk_url(self, page: FetchPage) -> str:
        match = re.search(
            r"https://lf-package-cn\.feishucdn\.com/obj/atsx-throne/hire-fe-prod/portal/campus/static/js/5918\.[^\"']+\.js",
            page.text,
            re.I,
        )
        if match:
            return match.group(0)
        for script_url in script_src_urls(page, allowed_hosts={"lf-package-cn.feishucdn.com"}, limit=24):
            if "/portal/campus/static/js/5918." in script_url:
                return script_url
        return ""

    def _extract_module_function(self, script_text: str, module_id: int) -> str:
        marker = f"{module_id}:function("
        start = script_text.find(marker)
        if start < 0:
            return ""
        func_start = script_text.find("function(", start)
        body_start = script_text.find("{", func_start)
        if func_start < 0 or body_start < 0:
            return ""
        depth = 1
        in_string: str | None = None
        escaped = False
        for index in range(body_start + 1, len(script_text)):
            char = script_text[index]
            if in_string is not None:
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == in_string:
                    in_string = None
                continue
            if char in {'"', "'", "`"}:
                in_string = char
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    return script_text[func_start : index + 1]
        return ""

    def _search_state(
        self,
        url: str,
        *,
        current_override: int | None = None,
        limit_override: int | None = None,
    ) -> dict[str, Any]:
        parsed = urlparse(url)
        params = httpx.QueryParams(parsed.query)
        limit = max(1, limit_override or int(params.get("limit") or "10"))
        current = max(1, current_override or int(params.get("current") or "1"))
        return {
            "keyword": params.get("keywords") or "",
            "limit": limit,
            "offset": (current - 1) * limit,
            "job_category_id_list": self._split_param(params.get("category")),
            "tag_id_list": self._split_param(params.get("tag")),
            "location_code_list": self._split_param(params.get("location")),
            "subject_id_list": self._split_param(params.get("project")),
            "recruitment_id_list": self._split_param(params.get("type")),
            "portal_type": 3,
            "job_function_id_list": self._split_param(params.get("functionCategory")),
            "storefront_id_list": self._split_param(params.get("storeFrontListString")),
            "portal_entrance": 1,
        }

    def _split_param(self, value: str | None) -> list[str]:
        return [item for item in (value or "").split(",") if item]

    def _new_api_session(self) -> _BytedanceApiSession:
        alphabet = string.ascii_lowercase + string.digits
        random_part = lambda length: "".join(random.choice(alphabet) for _ in range(length))
        return _BytedanceApiSession(
            cookie_values={
                "channel": "campus",
                "platform": "pc",
                "s_v_web_id": f"{random_part(12)}_{random_part(12)}",
                "device-id": str(random.randint(10**17, 10**18 - 1)),
            }
        )

    async def _request_api(
        self,
        client: httpx.AsyncClient,
        *,
        session: _BytedanceApiSession,
        module_source: str,
        referer_url: str,
        method: str,
        base_path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response | None:
        request_payload = json_body if method.upper() == "POST" else params or {}
        signed_path = await self._signed_path(
            module_source=module_source,
            base_path=base_path,
            method=method,
            request_payload=request_payload,
        )
        if not signed_path:
            return None
        response = await client.request(
            method.upper(),
            f"https://jobs.bytedance.com{signed_path}",
            headers=self._api_headers(
                referer_url=referer_url,
                session=session,
                include_content_type=method.upper() == "POST",
            ),
            json=json_body if method.upper() == "POST" else None,
        )
        if response.status_code != 405:
            return response
        csrf_token = await self._ensure_csrf_token(client, session, referer_url)
        if not csrf_token:
            return response
        return await client.request(
            method.upper(),
            f"https://jobs.bytedance.com{signed_path}",
            headers=self._api_headers(
                referer_url=referer_url,
                session=session,
                include_content_type=method.upper() == "POST",
            ),
            json=json_body if method.upper() == "POST" else None,
        )

    async def _ensure_csrf_token(
        self,
        client: httpx.AsyncClient,
        session: _BytedanceApiSession,
        referer_url: str,
    ) -> str:
        if session.csrf_token:
            return session.csrf_token
        response = await client.post(
            "https://jobs.bytedance.com/api/v1/csrf/token",
            headers=self._api_headers(
                referer_url=referer_url,
                session=session,
                include_content_type=True,
            ),
            json={"portal_entrance": 1},
        )
        if response.status_code != 200:
            return ""
        try:
            session.csrf_token = str(((response.json().get("data") or {}).get("token")) or "")
        except Exception:
            session.csrf_token = ""
        for header in response.headers.get_list("set-cookie"):
            cookie_key, cookie_value = self._cookie_from_header(header)
            if cookie_key and cookie_value:
                session.cookie_values[cookie_key] = cookie_value
        return session.csrf_token

    async def _signed_path(
        self,
        *,
        module_source: str,
        base_path: str,
        method: str,
        request_payload: dict[str, Any],
    ) -> str:
        query_string = self._query_string(request_payload)
        raw_path = f"{base_path}?{query_string}" if query_string else base_path
        signatures = await asyncio.to_thread(
            self._sign_requests,
            module_source,
            [{"url": raw_path, "body": request_payload if method.upper() == "POST" else {}}],
        )
        if not signatures:
            return ""
        separator = "&" if "?" in raw_path else "?"
        return f"{raw_path}{separator}_signature={quote(signatures[0], safe='')}"

    def _sign_requests(self, module_source: str, requests: list[dict[str, Any]]) -> list[str]:
        if not self._sign_helper_path.exists():
            return []
        payload = json.dumps(
            {
                "module_source": module_source,
                "requests": requests,
                "user_agent": self._user_agent,
                "href": "https://jobs.bytedance.com/campus/position",
                "referrer": "https://jobs.bytedance.com/campus/position",
            },
            ensure_ascii=False,
        )
        try:
            completed = subprocess.run(
                ["node", str(self._sign_helper_path)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
        except Exception:
            return []
        try:
            response = json.loads(completed.stdout or "{}")
        except Exception:
            return []
        signatures = response.get("signatures")
        if not isinstance(signatures, list):
            return []
        return [str(signature) for signature in signatures if signature]

    def _api_headers(
        self,
        *,
        referer_url: str,
        session: _BytedanceApiSession,
        include_content_type: bool,
    ) -> dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN",
            "env": "undefined",
            "Portal-Channel": "campus",
            "Portal-Platform": "pc",
            "referer": referer_url,
            "user-agent": self._user_agent,
            "website-path": "campus",
            "x-csrf-token": session.csrf_token or "undefined",
            "cookie": self._cookie_header(session.cookie_values),
        }
        if include_content_type:
            headers["content-type"] = "application/json"
        return headers

    def _cookie_header(self, cookie_values: dict[str, str]) -> str:
        return "; ".join(f"{key}={value}" for key, value in cookie_values.items() if value)

    def _cookie_from_header(self, header_value: str) -> tuple[str, str]:
        first = (header_value or "").split(";", 1)[0]
        if "=" not in first:
            return "", ""
        key, value = first.split("=", 1)
        return key.strip(), value.strip()

    def _query_string(self, payload: dict[str, Any]) -> str:
        parts = []
        for key, value in payload.items():
            if value is None:
                continue
            parts.append(f"{key}={quote(self._stringify_query_value(value), safe='')}")
        return "&".join(parts)

    def _stringify_query_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return ",".join(self._stringify_query_value(item) for item in value)
        return str(value)
