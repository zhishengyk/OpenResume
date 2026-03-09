from __future__ import annotations

import html
import json
import re

from ...services.official_sources import OfficialSource
from .base import ExtractedCandidate, FetchPage, OfficialExtractor
from .common import build_detail_extraction, find_script_blocks, walk_json_jobs


class MokaExtractor(OfficialExtractor):
    name = "moka"

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        lowered = f"{source.url} {page.final_url} {page.text[:8000]}".lower()
        return "mokahr.com" in lowered or "moka" in lowered

    def _embedded_payloads(self, page: FetchPage) -> list[object]:
        payloads: list[object] = []
        for block in find_script_blocks(page.text):
            content = (block.get("content") or "").strip()
            if not content:
                continue
            raw = html.unescape(content).strip().rstrip(";")
            try:
                payloads.append(json.loads(raw))
            except Exception:
                continue

        decoded_page = html.unescape(page.text)
        for pattern in [
            re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', re.S),
            re.compile(r'window\.__NUXT__\s*=\s*(\{.*?\});', re.S),
        ]:
            match = pattern.search(decoded_page)
            if not match:
                continue
            try:
                payloads.append(json.loads(match.group(1)))
            except Exception:
                continue
        return payloads

    def extract_candidates(
        self,
        source: OfficialSource,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> list[ExtractedCandidate]:
        candidates: list[ExtractedCandidate] = []
        for payload in self._embedded_payloads(page):
            candidates.extend(
                walk_json_jobs(
                    payload=payload,
                    company_url=page.final_url,
                    requested_cities=requested_cities,
                    source_name="moka-json",
                )
            )
        for candidate in candidates:
            candidate.raw_payload["extractor"] = self.name
            candidate.raw_payload["entry_url"] = page.final_url
        return candidates

    def extract_detail(
        self,
        source: OfficialSource,
        candidate: ExtractedCandidate,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ):
        return build_detail_extraction(candidate, page, requested_targets, requested_cities)
