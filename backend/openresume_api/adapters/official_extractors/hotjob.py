from __future__ import annotations

import httpx

from ...services.official_sources import OfficialSource
from .base import ExtractedCandidate, FetchPage, OfficialExtractor
from .common import build_detail_extraction


class HotjobExtractor(OfficialExtractor):
    name = "hotjob"

    async def prepare_source_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        page: FetchPage,
    ) -> FetchPage:
        if "wecruit/common/getSLD" not in page.text:
            return page
        response = await client.post(
            f"{page.final_url.rstrip('/')}/wecruit/common/getSLD",
            data={"sld": source.host},
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        link = (
            payload.get("data", {}).get("linkData", {}).get("wtLink")
            or payload.get("data", {}).get("linkData", {}).get("link")
        )
        if not isinstance(link, str) or not link.strip():
            return page
        resolved = await client.get(link, follow_redirects=True)
        resolved.raise_for_status()
        return FetchPage(
            requested_url=link,
            final_url=str(resolved.url),
            text=resolved.text,
            status_code=resolved.status_code,
            content_type=resolved.headers.get("content-type", ""),
        )

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        lowered = f"{source.url} {page.final_url} {page.text[:4000]}".lower()
        return "hotjob" in lowered or "zhiye.com" in lowered or "wecruit/common/getsld" in lowered

    def extract_candidates(
        self,
        source: OfficialSource,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> list[ExtractedCandidate]:
        return []

    def extract_detail(
        self,
        source: OfficialSource,
        candidate: ExtractedCandidate,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ):
        return build_detail_extraction(candidate, page, requested_targets, requested_cities)
