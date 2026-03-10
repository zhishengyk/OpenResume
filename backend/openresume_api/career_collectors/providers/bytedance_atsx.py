from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
import string
import subprocess
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class HeaderProfile:
    portal_channel: str
    website_path: str
    cookie_channel: str


@dataclass(frozen=True)
class BytedanceVariantConfig:
    variant: str
    entry_url: str
    search_path: str
    detail_path_template: str
    portal_type: int
    header_profiles: tuple[HeaderProfile, ...]

    def search_page_url(self, keyword: str, *, current: int = 1, limit: int = 10) -> str:
        return (
            f"https://jobs.bytedance.com{self.search_path}"
            f"?keywords={quote(keyword)}&current={current}&limit={limit}"
        )

    def detail_url(self, job_id: str) -> str:
        return self.detail_path_template.format(job_id=job_id)


@dataclass
class SignedSession:
    header_profile: HeaderProfile
    cookie_values: dict[str, str]
    csrf_token: str | None = None


VARIANT_CONFIGS = {
    "experienced": BytedanceVariantConfig(
        variant="experienced",
        entry_url="https://jobs.bytedance.com/",
        search_path="/experienced/position/list",
        detail_path_template="https://jobs.bytedance.com/experienced/position/{job_id}/detail",
        portal_type=2,
        header_profiles=(
            HeaderProfile("office", "society", "office"),
            HeaderProfile("campus", "campus", "campus"),
        ),
    ),
    "campus": BytedanceVariantConfig(
        variant="campus",
        entry_url="https://jobs.bytedance.com/campus",
        search_path="/campus/position/list",
        detail_path_template="https://jobs.bytedance.com/campus/position/{job_id}/detail",
        portal_type=3,
        header_profiles=(
            HeaderProfile("campus", "campus", "campus"),
            HeaderProfile("office", "society", "office"),
        ),
    ),
    "internship": BytedanceVariantConfig(
        variant="internship",
        entry_url="https://jobs.bytedance.com/campus",
        search_path="/campus/position/list",
        detail_path_template="https://jobs.bytedance.com/campus/position/{job_id}/detail",
        portal_type=3,
        header_profiles=(
            HeaderProfile("campus", "campus", "campus"),
            HeaderProfile("office", "society", "office"),
        ),
    ),
}


class BytedanceAtsxClient:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        user_agent: str,
        max_pages: int,
        page_size: int,
        node_command: str = "node",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.max_pages = max_pages
        self.page_size = max(1, page_size)
        self.node_command = node_command
        self.sign_script_path = Path(__file__).with_name("bytedance_sign.cjs")
        self._module_cache: dict[str, str] = {}

    def collect_jobs(
        self,
        *,
        variant: str,
        keywords: list[str],
    ) -> list[dict[str, Any]]:
        config = VARIANT_CONFIGS[variant]
        with httpx.Client(
            timeout=self.timeout_seconds,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        ) as client:
            homepage = client.get(config.entry_url)
            homepage.raise_for_status()
            module_source = self._load_sign_module_source(
                client,
                cache_key=config.variant,
                page_html=homepage.text,
            )
            deduped: dict[str, dict[str, Any]] = {}
            for keyword in keywords:
                items = self._collect_keyword_jobs(
                    client,
                    config=config,
                    module_source=module_source,
                    keyword=keyword,
                )
                for item in items:
                    job_id = str(item.get("id") or "")
                    if not job_id:
                        continue
                    deduped.setdefault(job_id, item)
            return sorted(
                deduped.values(),
                key=lambda item: int(item.get("publish_time") or 0),
                reverse=True,
            )

    def fetch_detail(
        self,
        *,
        variant: str,
        job_id: str,
        keyword: str,
    ) -> dict[str, Any]:
        config = VARIANT_CONFIGS[variant]
        with httpx.Client(
            timeout=self.timeout_seconds,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        ) as client:
            homepage = client.get(config.entry_url)
            homepage.raise_for_status()
            module_source = self._load_sign_module_source(
                client,
                cache_key=config.variant,
                page_html=homepage.text,
            )
            referer = config.search_page_url(keyword)
            session = self._establish_session(
                client,
                config=config,
                module_source=module_source,
                referer_url=referer,
                keyword=keyword,
            )
            response = self._request_api(
                client,
                session=session,
                module_source=module_source,
                referer_url=referer,
                method="GET",
                base_path=f"/api/v1/job/posts/{job_id}",
                params={
                    "portal_type": config.portal_type,
                    "source_job_post_id": job_id,
                    "with_recommend": False,
                },
            )
            if response.status_code != 200:
                response.raise_for_status()
            payload = response.json()
            detail = ((payload.get("data") or {}).get("job_post_detail")) or {}
            return detail if isinstance(detail, dict) else {}

    def detail_url(self, *, variant: str, job_id: str) -> str:
        return VARIANT_CONFIGS[variant].detail_url(job_id)

    def _collect_keyword_jobs(
        self,
        client: httpx.Client,
        *,
        config: BytedanceVariantConfig,
        module_source: str,
        keyword: str,
    ) -> list[dict[str, Any]]:
        referer = config.search_page_url(keyword)
        session = self._establish_session(
            client,
            config=config,
            module_source=module_source,
            referer_url=referer,
            keyword=keyword,
        )
        items: list[dict[str, Any]] = []
        limit = self.page_size
        for current in range(1, max(1, self.max_pages) + 1):
            response = self._request_api(
                client,
                session=session,
                module_source=module_source,
                referer_url=referer,
                method="POST",
                base_path="/api/v1/search/job/posts",
                json_body=self._search_payload(
                    keyword,
                    current=current,
                    limit=limit,
                    portal_type=config.portal_type,
                ),
            )
            if response.status_code != 200:
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
            if total and current * limit >= total:
                break
        return items

    def _establish_session(
        self,
        client: httpx.Client,
        *,
        config: BytedanceVariantConfig,
        module_source: str,
        referer_url: str,
        keyword: str,
    ) -> SignedSession:
        last_error: RuntimeError | None = None
        for profile in config.header_profiles:
            session = SignedSession(
                header_profile=profile,
                cookie_values=self._new_cookie_values(profile.cookie_channel),
            )
            try:
                response = self._request_api(
                    client,
                    session=session,
                    module_source=module_source,
                    referer_url=referer_url,
                    method="POST",
                    base_path="/api/v1/search/job/posts",
                    json_body=self._search_payload(
                        keyword,
                        current=1,
                        limit=1,
                        portal_type=config.portal_type,
                    ),
                )
            except Exception as error:  # pragma: no cover
                last_error = RuntimeError(str(error))
                continue

            if response.status_code != 200:
                last_error = RuntimeError(f"unexpected status {response.status_code}")
                continue

            try:
                data = response.json().get("data") or {}
            except Exception as error:  # pragma: no cover
                last_error = RuntimeError(str(error))
                continue

            if isinstance(data.get("job_post_list"), list):
                return session

        raise RuntimeError(str(last_error or "无法建立字节跳动 API 会话"))

    def _load_sign_module_source(
        self,
        client: httpx.Client,
        *,
        cache_key: str,
        page_html: str,
    ) -> str:
        cached = self._module_cache.get(cache_key)
        if cached:
            return cached
        script_urls = re.findall(r'<script[^>]+src="([^"]+)"', page_html)
        for script_url in script_urls:
            if "/static/js/" not in script_url:
                continue
            response = client.get(script_url)
            if response.status_code != 200:
                continue
            module_source = self._extract_module_function(response.text, 57195)
            if module_source:
                self._module_cache[cache_key] = module_source
                return module_source
        raise RuntimeError("无法找到字节跳动签名模块 57195")

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

    def _request_api(
        self,
        client: httpx.Client,
        *,
        session: SignedSession,
        module_source: str,
        referer_url: str,
        method: str,
        base_path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        request_payload = json_body if method.upper() == "POST" else params or {}
        signed_path = self._signed_path(
            module_source=module_source,
            base_path=base_path,
            method=method,
            request_payload=request_payload,
            referer_url=referer_url,
        )
        response = client.request(
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
        csrf_token = self._ensure_csrf_token(client, session, referer_url)
        if not csrf_token:
            return response
        return client.request(
            method.upper(),
            f"https://jobs.bytedance.com{signed_path}",
            headers=self._api_headers(
                referer_url=referer_url,
                session=session,
                include_content_type=method.upper() == "POST",
            ),
            json=json_body if method.upper() == "POST" else None,
        )

    def _ensure_csrf_token(
        self,
        client: httpx.Client,
        session: SignedSession,
        referer_url: str,
    ) -> str:
        if session.csrf_token:
            return session.csrf_token
        response = client.post(
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
            key, value = self._cookie_from_header(header)
            if key and value:
                session.cookie_values[key] = value
        return session.csrf_token

    def _signed_path(
        self,
        *,
        module_source: str,
        base_path: str,
        method: str,
        request_payload: dict[str, Any],
        referer_url: str,
    ) -> str:
        query_string = self._query_string(request_payload)
        raw_path = f"{base_path}?{query_string}" if query_string else base_path
        payload = json.dumps(
            {
                "module_source": module_source,
                "requests": [
                    {
                        "url": raw_path,
                        "body": request_payload if method.upper() == "POST" else {},
                    }
                ],
                "user_agent": self.user_agent,
                "href": referer_url,
                "referrer": referer_url,
            },
            ensure_ascii=False,
        )
        completed = subprocess.run(
            [self.node_command, str(self.sign_script_path)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        response = json.loads(completed.stdout or "{}")
        signatures = response.get("signatures") or []
        if not signatures:
            raise RuntimeError("字节跳动签名生成失败")
        separator = "&" if "?" in raw_path else "?"
        return f"{raw_path}{separator}_signature={quote(str(signatures[0]), safe='')}"

    def _api_headers(
        self,
        *,
        referer_url: str,
        session: SignedSession,
        include_content_type: bool,
    ) -> dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN",
            "env": "undefined",
            "Portal-Channel": session.header_profile.portal_channel,
            "Portal-Platform": "pc",
            "referer": referer_url,
            "user-agent": self.user_agent,
            "website-path": session.header_profile.website_path,
            "x-csrf-token": session.csrf_token or "undefined",
            "cookie": self._cookie_header(session.cookie_values),
        }
        if include_content_type:
            headers["content-type"] = "application/json"
        return headers

    def _search_payload(
        self,
        keyword: str,
        *,
        current: int,
        limit: int,
        portal_type: int,
    ) -> dict[str, Any]:
        return {
            "keyword": keyword,
            "limit": limit,
            "offset": (current - 1) * limit,
            "job_category_id_list": [],
            "tag_id_list": [],
            "location_code_list": [],
            "subject_id_list": [],
            "recruitment_id_list": [],
            "portal_type": portal_type,
            "job_function_id_list": [],
            "storefront_id_list": [],
            "portal_entrance": 1,
        }

    def _new_cookie_values(self, channel: str) -> dict[str, str]:
        alphabet = string.ascii_lowercase + string.digits
        random_part = lambda length: "".join(random.choice(alphabet) for _ in range(length))
        return {
            "channel": channel,
            "platform": "pc",
            "s_v_web_id": f"{random_part(12)}_{random_part(12)}",
            "device-id": str(random.randint(10**17, 10**18 - 1)),
        }

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
