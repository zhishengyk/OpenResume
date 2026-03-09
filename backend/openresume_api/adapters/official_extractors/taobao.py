from __future__ import annotations

import re

import httpx

from ...services.official_sources import OfficialSource
from .base import FetchPage, OfficialExtractor
from .common import (
    build_detail_extraction,
    candidate_detail_key,
    merge_candidates,
    normalize_title,
    normalize_whitespace,
)
from .generic import GenericExtractor
from .json_ssr import JsonSsrExtractor
from .site_helpers import (
    anchor_urls,
    build_candidate_from_payload,
    bundle_pages,
    first_nested_string,
    first_string,
    json_payloads_from_page,
    matching_payloads,
    page_query_value,
    payload_detail_extraction,
    payload_dicts,
    response_to_page,
    safe_fetch_page,
    script_src_urls,
    stringify_value,
    text_urls,
    unbundle_pages,
)


class TaobaoExtractor(OfficialExtractor):
    name = "taobao"
    _position_search_endpoint = "https://talent.taotian.com/position/search"
    _search_condition_endpoint = "https://talent.taotian.com/searchCondition/list"

    _json = JsonSsrExtractor()
    _generic = GenericExtractor()

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        lowered = f"{source.url} {page.final_url} {page.text[:5000]}".lower()
        return any(host in lowered for host in ("zhaopin.taobao.com", "talent.taotian.com"))

    async def prepare_source_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        page: FetchPage,
    ) -> FetchPage:
        pages = [page]
        allowed_hosts = {"zhaopin.taobao.com", "talent.taotian.com"}
        visited = {candidate for candidate in [page.final_url, page.requested_url] if candidate}
        queue = self._position_list_urls(page, allowed_hosts)
        queue.extend(
            url
            for url in [
                "https://talent.taotian.com/campus/position-list?campusType=freshman&lang=zh",
                "https://talent.taotian.com/campus/position-list?campusType=internship&lang=zh",
            ]
            if url not in visited
        )

        while queue and len(pages) < 10:
            next_url = queue.pop(0)
            if next_url in visited:
                continue
            visited.add(next_url)
            fetched = await safe_fetch_page(client, next_url)
            if fetched is None:
                continue
            pages.append(fetched)
            for api_page in await self._api_pages_for_listing(client, fetched):
                pages.append(api_page)
            for extra_url in self._position_list_urls(fetched, allowed_hosts):
                if extra_url not in visited and extra_url not in queue:
                    queue.append(extra_url)
            for script_url in script_src_urls(fetched, allowed_hosts=allowed_hosts, limit=4):
                if script_url not in visited and script_url not in queue:
                    queue.append(script_url)
            for api_url in self._api_urls(fetched, allowed_hosts):
                if api_url not in visited and api_url not in queue:
                    queue.append(api_url)

        return bundle_pages(page, pages[1:], {"site": self.name})

    async def _api_pages_for_listing(
        self,
        client: httpx.AsyncClient,
        page: FetchPage,
    ) -> list[FetchPage]:
        if "talent.taotian.com" not in page.final_url.lower():
            return []
        if "position-list" not in page.final_url.lower():
            return []

        token_match = re.search(r'__token__\s*:\s*"([^"]+)"', page.text)
        if token_match is None:
            return []

        category_type = page_query_value(page.final_url, "campusType")
        category_candidates = [category_type] if category_type else []
        campus_entry_match = re.search(r'campusApplyEntry\s*:\s*"([^"]+)"', page.text)
        if campus_entry_match:
            category_candidates.append(campus_entry_match.group(1).strip())
        category_candidates.extend(["internship", "freshman"])

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://talent.taotian.com",
            "Referer": page.final_url,
        }
        token = token_match.group(1)
        fetched_pages: list[FetchPage] = []
        seen_request_urls: set[str] = set()
        for category in dict.fromkeys(candidate for candidate in category_candidates if candidate):
            base_payload = {
                "channel": "campus",
                "language": "zh_CN",
                "pageIndex": 1,
                "pageSize": 20,
                "batchId": "",
                "categoryType": category,
            }
            try:
                await client.post(
                    f"{self._search_condition_endpoint}?_csrf={token}",
                    json={
                        "channel": "campus",
                        "language": "zh_CN",
                        "categoryType": category,
                        "batchId": "",
                    },
                    headers=headers,
                )
                response = await client.post(
                    f"{self._position_search_endpoint}?_csrf={token}",
                    json=base_payload,
                    headers=headers,
                )
                response.raise_for_status()
            except Exception:
                continue

            first_page = response_to_page(
                f"{self._position_search_endpoint}?_csrf={token}&pageIndex=1&categoryType={category}",
                response,
            )
            first_page = FetchPage(
                requested_url=first_page.requested_url,
                final_url=page.final_url,
                text=first_page.text,
                status_code=first_page.status_code,
                content_type=first_page.content_type,
            )
            request_key = f"{category}:1"
            if request_key not in seen_request_urls:
                fetched_pages.append(first_page)
                seen_request_urls.add(request_key)

            try:
                payload = response.json()
            except Exception:
                continue
            content = payload.get("content") or {}
            total_count = int(content.get("totalCount") or 0)
            if total_count <= 20:
                continue

            total_pages = min((total_count + 19) // 20, 5)
            for page_index in range(2, total_pages + 1):
                if len(fetched_pages) >= 5:
                    break
                try:
                    next_response = await client.post(
                        f"{self._position_search_endpoint}?_csrf={token}",
                        json={**base_payload, "pageIndex": page_index},
                        headers=headers,
                    )
                    next_response.raise_for_status()
                except Exception:
                    break
                request_key = f"{category}:{page_index}"
                if request_key in seen_request_urls:
                    continue
                next_page = response_to_page(
                    (
                        f"{self._position_search_endpoint}?_csrf={token}"
                        f"&pageIndex={page_index}&categoryType={category}"
                    ),
                    next_response,
                )
                fetched_pages.append(
                    FetchPage(
                        requested_url=next_page.requested_url,
                        final_url=page.final_url,
                        text=next_page.text,
                        status_code=next_page.status_code,
                        content_type=next_page.content_type,
                    )
                )
                seen_request_urls.add(request_key)
        return fetched_pages

    def _position_list_urls(self, page: FetchPage, allowed_hosts: set[str]) -> list[str]:
        urls = anchor_urls(
            page,
            allowed_hosts=allowed_hosts,
            include_keywords=("position-list", "position-detail", "campus"),
        )
        urls.extend(
            text_urls(
                page.text,
                base_url=page.final_url,
                allowed_hosts=allowed_hosts,
                include_keywords=("position-list", "position-detail", "campus"),
            )
        )
        for match in re.finditer(
            r"https://talent\.taotian\.com/campus/position-(?:list|detail)\?[^\"'\s<>]+",
            page.text,
            re.I,
        ):
            urls.append(match.group(0))
        return list(dict.fromkeys(urls))

    def _api_urls(self, page: FetchPage, allowed_hosts: set[str]) -> list[str]:
        urls = text_urls(
            page.text,
            base_url=page.final_url,
            allowed_hosts=allowed_hosts,
            include_keywords=("api", "position", "search", ".json"),
        )
        return [
            url
            for url in urls
            if "/api/" in url.lower() or url.lower().endswith(".json") or "position-" in url.lower()
        ]

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
            for payload in json_payloads_from_page(bundled_page):
                candidates.extend(
                    self._walk_taobao_jobs(
                        payload,
                        company_url=bundled_page.final_url,
                        requested_cities=requested_cities,
                    )
                )
            candidates.extend(
                self._regex_candidates(
                    bundled_page,
                    requested_cities=requested_cities,
                )
            )
        deduped = {}
        for candidate in candidates:
            candidate.raw_payload["extractor"] = self.name
            key = candidate_detail_key(candidate)
            existing = deduped.get(key)
            deduped[key] = merge_candidates(existing, candidate) if existing else candidate
        return [candidate for candidate in deduped.values() if self._is_real_position_candidate(candidate)]

    def _is_real_position_candidate(self, candidate) -> bool:
        detail_url = (candidate.detail_url or "").lower()
        if "talent.taotian.com" in detail_url:
            return "/campus/position-detail" in detail_url and bool(
                page_query_value(candidate.detail_url, "positionId")
            )
        if "zhaopin.taobao.com" in detail_url:
            return (
                ("job_detail.htm" in detail_url or bool(page_query_value(candidate.detail_url, "id")))
                and "categoryfirstid" not in detail_url
                and "categorysecondid" not in detail_url
            )
        return False

    def _walk_taobao_jobs(
        self,
        payload,
        *,
        company_url: str,
        requested_cities: list[str],
    ):
        candidates = []
        for item in payload_dicts(payload):
            title = first_nested_string(
                item,
                ["positionName", "positionTitle", "title", "name", "jobName", "postName"],
            )
            detail_url = first_string(item, ["detailUrl", "jobUrl", "url", "link", "positionUrl"])
            position_id = first_string(item, ["positionId", "jobId", "id", "postId"])
            if not detail_url and position_id and position_id.isdigit():
                detail_url = (
                    "https://talent.taotian.com/campus/position-detail"
                    f"?lang=zh&positionId={position_id}"
                )
            description = stringify_value(
                item.get("description")
                or item.get("jobDescription")
                or item.get("requirement")
                or item.get("responsibility")
                or item.get("requirement")
                or item.get("content")
                or item.get("summary")
            )
            city_text = stringify_value(
                item.get("workLocations")
                or item.get("workLocation")
                or item.get("city")
                or item.get("location")
                or item.get("baseCity")
                or item.get("locationName")
            ) or first_nested_string(
                item,
                ["city", "workLocation", "location", "baseCity", "locationName"],
            )
            department = first_nested_string(
                item,
                ["department", "deptName", "dept", "categoryName", "buName", "teamName"],
            )
            candidate = build_candidate_from_payload(
                title=title,
                detail_url=detail_url,
                company_url=company_url,
                requested_cities=requested_cities,
                source_name="script-json",
                payload=item,
                description=description,
                city_text=city_text,
                department=department,
            )
            if candidate is None:
                continue
            candidate.raw_payload["api_source"] = "taobao-api"
            if position_id:
                candidate.raw_payload["position_id"] = position_id
            candidates.append(candidate)
        return candidates

    def _regex_candidates(self, page: FetchPage, *, requested_cities: list[str]):
        candidates = []
        pattern = re.compile(
            r'"(?:positionName|positionTitle|title|name)"\s*:\s*"([^"]+)"'
            r'(?:(?:(?!\{|\}).){0,800}?)"(?:positionId|id)"\s*:\s*"?(\d+)"?',
            re.S,
        )
        for title, position_id in pattern.findall(page.text):
            resolved_url = (
                "https://talent.taotian.com/campus/position-detail"
                f"?lang=zh&positionId={position_id}"
            )
            candidate = build_candidate_from_payload(
                title=title,
                detail_url=resolved_url,
                company_url=page.final_url,
                requested_cities=requested_cities,
                source_name="taobao-regex",
                payload={"title": title, "positionId": position_id, "detailUrl": resolved_url},
                description=title,
            )
            if candidate is None:
                continue
            if position_id:
                candidate.raw_payload["position_id"] = position_id
            candidates.append(candidate)
        return candidates

    def extract_detail(
        self,
        source: OfficialSource,
        candidate,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ):
        pages, _ = unbundle_pages(page)
        best_page = max(pages, key=lambda item: len(normalize_whitespace(item.text)))
        detail = build_detail_extraction(candidate, best_page, requested_targets, requested_cities)
        if detail.classification == "job_detail" and len(normalize_whitespace(detail.text)) >= 200:
            return detail

        payloads = list(json_payloads_from_page(best_page))
        if candidate.raw_payload.get("payload"):
            payloads.insert(0, candidate.raw_payload["payload"])
        needles = [
            str(candidate.raw_payload.get("position_id") or ""),
            normalize_title(candidate.title),
        ]
        for payload in matching_payloads(payloads, needles):
            synthetic = payload_detail_extraction(
                candidate=candidate,
                page=best_page,
                payload=payload,
                requested_cities=requested_cities,
                responsibilities_keys=(
                    "responsibility",
                    "responsibilities",
                    "jobResponsibility",
                    "jobResponsibilities",
                ),
                requirements_keys=(
                    "requirement",
                    "requirements",
                    "jobRequirement",
                    "jobRequirements",
                    "qualification",
                    "qualifications",
                ),
                description_keys=("description", "jobDescription", "content", "summary"),
                location_keys=("city", "workLocation", "location", "baseCity", "locationName"),
                department_keys=("department", "deptName", "dept", "categoryName", "buName"),
                title_keys=("positionName", "positionTitle", "title", "name", "jobName"),
            )
            if synthetic is not None:
                return synthetic
        return detail
