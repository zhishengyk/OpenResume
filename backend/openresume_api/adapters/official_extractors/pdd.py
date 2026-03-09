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
    stringify_value,
    text_urls,
    unbundle_pages,
)


class PddExtractor(OfficialExtractor):
    name = "pdd"
    _position_list_endpoint = "https://careers.pddglobalhr.com/api/careers/api/recruit/position/list"
    _intern_list_endpoint = (
        "https://careers.pddglobalhr.com/api/careers/api/recruit/position/train/list"
    )
    _position_detail_endpoint = (
        "https://careers.pddglobalhr.com/api/careers/api/recruit/position/detail"
    )

    _json = JsonSsrExtractor()

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        lowered = f"{source.url} {page.final_url} {page.text[:5000]}".lower()
        return "pddglobalhr.com" in lowered

    async def prepare_source_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        page: FetchPage,
    ) -> FetchPage:
        pages = [page]
        allowed_hosts = {"careers.pddglobalhr.com"}
        visited = {candidate for candidate in [page.final_url, page.requested_url] if candidate}
        queue = self._entry_urls(page, allowed_hosts)
        queue.extend(
            url
            for url in [
                "https://careers.pddglobalhr.com/campus/grad",
                "https://careers.pddglobalhr.com/campus/intern",
            ]
            if url not in visited
        )

        while queue and len(pages) < 12:
            next_url = queue.pop(0)
            if next_url in visited:
                continue
            visited.add(next_url)
            fetched = await safe_fetch_page(client, next_url)
            if fetched is None:
                continue
            pages.append(fetched)
            for api_page in await self._api_pages_for_scope(client, fetched):
                pages.append(api_page)

        return bundle_pages(page, pages[1:], {"site": self.name})

    async def prepare_detail_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        candidate,
        page: FetchPage,
    ) -> FetchPage:
        pages = [page]
        detail_page = await self._detail_api_page(client, candidate, page)
        if detail_page is not None:
            pages.append(detail_page)

        return bundle_pages(page, pages[1:], {"site": self.name, "detail": candidate.detail_url})

    async def _api_pages_for_scope(
        self,
        client: httpx.AsyncClient,
        page: FetchPage,
    ) -> list[FetchPage]:
        scope = self._scope_for_url(page.final_url)
        if not scope:
            return []

        endpoint = self._intern_list_endpoint if scope == "intern" else self._position_list_endpoint
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://careers.pddglobalhr.com",
            "Referer": page.final_url,
        }
        fetched_pages: list[FetchPage] = []
        try:
            response = await client.post(
                endpoint,
                json={"page": 1, "pageSize": 20},
                headers=headers,
            )
            response.raise_for_status()
        except Exception:
            return fetched_pages

        first_page = response_to_page(f"{endpoint}?page=1&pageSize=20", response)
        fetched_pages.append(
            FetchPage(
                requested_url=first_page.requested_url,
                final_url=page.final_url,
                text=first_page.text,
                status_code=first_page.status_code,
                content_type=first_page.content_type,
            )
        )

        try:
            payload = response.json()
        except Exception:
            return fetched_pages
        result = payload.get("result") or {}
        total_count = int(result.get("total") or 0)
        if total_count <= 20:
            return fetched_pages

        total_pages = min((total_count + 19) // 20, 5)
        for page_index in range(2, total_pages + 1):
            if len(fetched_pages) >= 5:
                break
            try:
                next_response = await client.post(
                    endpoint,
                    json={"page": page_index, "pageSize": 20},
                    headers=headers,
                )
                next_response.raise_for_status()
            except Exception:
                break
            next_page = response_to_page(f"{endpoint}?page={page_index}&pageSize=20", next_response)
            fetched_pages.append(
                FetchPage(
                    requested_url=next_page.requested_url,
                    final_url=page.final_url,
                    text=next_page.text,
                    status_code=next_page.status_code,
                    content_type=next_page.content_type,
                )
            )
        return fetched_pages

    async def _detail_api_page(
        self,
        client: httpx.AsyncClient,
        candidate,
        page: FetchPage,
    ) -> FetchPage | None:
        position_id = str(
            candidate.raw_payload.get("position_id")
            or page_query_value(candidate.detail_url, "positionId")
            or ""
        )
        if not position_id:
            return None

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://careers.pddglobalhr.com",
            "Referer": candidate.detail_url,
        }
        try:
            response = await client.post(
                self._position_detail_endpoint,
                json={"id": position_id},
                headers=headers,
            )
            response.raise_for_status()
        except Exception:
            return None

        detail_page = response_to_page(self._position_detail_endpoint, response)
        return FetchPage(
            requested_url=detail_page.requested_url,
            final_url=page.final_url or candidate.detail_url,
            text=detail_page.text,
            status_code=detail_page.status_code,
            content_type=detail_page.content_type,
        )

    def _entry_urls(self, page: FetchPage, allowed_hosts: set[str]) -> list[str]:
        urls = anchor_urls(
            page,
            allowed_hosts=allowed_hosts,
            include_keywords=("campus", "grad", "intern", "detail"),
        )
        urls.extend(
            text_urls(
                page.text,
                base_url=page.final_url,
                allowed_hosts=allowed_hosts,
                include_keywords=("campus", "grad", "intern", "detail"),
            )
        )
        return list(dict.fromkeys(urls))

    def _api_urls(self, page: FetchPage, allowed_hosts: set[str]) -> list[str]:
        urls = text_urls(
            page.text,
            base_url=page.final_url,
            allowed_hosts=allowed_hosts,
            include_keywords=("api", "job", "position", "campus", "grad", "intern", ".json"),
        )
        return [
            url
            for url in urls
            if "/api/" in url.lower()
            or url.lower().endswith(".json")
            or "/campus/grad/detail" in url.lower()
            or "/campus/intern/detail" in url.lower()
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
            for payload in json_payloads_from_page(bundled_page):
                candidates.extend(
                    self._walk_pdd_jobs(
                        payload,
                        company_url=bundled_page.final_url,
                        requested_cities=requested_cities,
                    )
                )
            candidates.extend(self._regex_candidates(bundled_page, requested_cities=requested_cities))
        deduped = {}
        for candidate in candidates:
            candidate.raw_payload["extractor"] = self.name
            key = candidate_detail_key(candidate)
            existing = deduped.get(key)
            deduped[key] = merge_candidates(existing, candidate) if existing else candidate
        return list(deduped.values())

    def _scope_for_url(self, url: str) -> str:
        lowered = url.lower()
        if "/campus/intern" in lowered:
            return "intern"
        if "/campus/grad" in lowered:
            return "grad"
        return ""

    def _walk_pdd_jobs(
        self,
        payload,
        *,
        company_url: str,
        requested_cities: list[str],
    ):
        scope = self._scope_for_url(company_url)
        candidates = []
        for item in payload_dicts(payload):
            title = first_nested_string(
                item,
                ["positionName", "name", "title", "postName", "positionTitle", "jobName"],
            )
            detail_url = first_string(item, ["detailUrl", "jobUrl", "url", "link"])
            position_id = first_string(item, ["id", "positionId", "code"])
            if not detail_url and position_id and scope:
                detail_url = (
                    f"https://careers.pddglobalhr.com/campus/{scope}/detail"
                    f"?positionId={position_id}"
                )
            description = stringify_value(
                item.get("description")
                or item.get("jobDescription")
                or item.get("jobDuty")
                or item.get("serveRequirement")
                or item.get("responsibility")
                or item.get("requirement")
                or item.get("summary")
                or item.get("content")
            )
            city_text = stringify_value(
                item.get("workLocationName")
                or item.get("workLocation")
                or item.get("city")
                or item.get("location")
                or item.get("locationName")
                or item.get("cityName")
            ) or first_nested_string(item, ["city", "location", "workLocation", "locationName", "cityName"])
            department = first_nested_string(item, ["jobName", "recruitTypeName", "department", "team"])
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
            candidate.raw_payload["api_source"] = "pdd-api"
            if position_id:
                candidate.raw_payload["position_id"] = position_id
            if scope:
                candidate.raw_payload["detail_scope"] = scope
            candidates.append(candidate)
        return candidates

    def _regex_candidates(self, page: FetchPage, *, requested_cities: list[str]):
        candidates = []
        pattern = re.compile(
            r'"(?:positionName|positionTitle|title|name)"\s*:\s*"([^"]+)"'
            r'(?:(?:(?!\{|\}).){0,1000}?)"id"\s*:\s*"([0-9a-f-]{8,})"',
            re.S,
        )
        scope = self._scope_for_url(page.final_url)
        for title, position_id in pattern.findall(page.text):
            resolved_url = ""
            if position_id and scope:
                resolved_url = (
                    f"https://careers.pddglobalhr.com/campus/{scope}/detail"
                    f"?positionId={position_id}"
                )
            candidate = build_candidate_from_payload(
                title=title,
                detail_url=resolved_url,
                company_url=page.final_url,
                requested_cities=requested_cities,
                source_name="pdd-regex",
                payload={"title": title, "detailUrl": resolved_url, "id": position_id},
                description=title,
            )
            if candidate is None:
                continue
            if position_id:
                candidate.raw_payload["position_id"] = position_id
            if scope:
                candidate.raw_payload["detail_scope"] = scope
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

        payloads = []
        for bundled_page in pages:
            payloads.extend(json_payloads_from_page(bundled_page))
        if candidate.raw_payload.get("payload"):
            payloads.insert(0, candidate.raw_payload["payload"])

        needles = [
            str(
                candidate.raw_payload.get("position_id")
                or page_query_value(candidate.detail_url, "positionId")
                or ""
            ),
            normalize_title(candidate.title),
        ]
        for payload in matching_payloads(payloads, needles):
            synthetic = payload_detail_extraction(
                candidate=candidate,
                page=best_page,
                payload=payload,
                requested_cities=requested_cities,
                responsibilities_keys=("jobDuty", "responsibility", "responsibilities"),
                requirements_keys=("serveRequirement", "requirement", "requirements"),
                description_keys=("bonus", "description", "jobDescription", "summary", "content"),
                location_keys=("workLocationName", "workLocation", "city", "location", "locationName"),
                department_keys=("jobName", "recruitTypeName", "department", "team"),
                title_keys=("name", "positionName", "positionTitle", "jobName", "title"),
            )
            if synthetic is not None:
                return synthetic
        return detail
