from __future__ import annotations

import html
import json
import re

from ...services.official_sources import OfficialSource
from .base import ExtractedCandidate, FetchPage, OfficialExtractor
from .common import build_detail_extraction, find_script_blocks, walk_json_jobs


class JsonSsrExtractor(OfficialExtractor):
    name = "json_ssr"

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        if "json" in page.content_type.lower():
            return True
        for block in find_script_blocks(page.text):
            block_type = (block.get("type") or "").lower()
            block_id = (block.get("id") or "").lower()
            if "json" in block_type or block_id in {"__next_data__", "__nuxt__", "js-websiteinfo"}:
                return True
        return False

    def _parse_payloads(self, page: FetchPage) -> list[object]:
        payloads: list[object] = []
        if "json" in page.content_type.lower():
            try:
                payloads.append(json.loads(page.text))
            except Exception:
                pass
        for block in find_script_blocks(page.text):
            content = block.get("content") or ""
            block_type = (block.get("type") or "").lower()
            block_id = (block.get("id") or "").lower()
            if "json" not in block_type and block_id not in {"__next_data__", "__nuxt__", "js-websiteinfo"}:
                continue
            raw = html.unescape(content).strip()
            if not raw:
                continue
            raw = re.sub(r"^\s*window\.[A-Z0-9_]+\s*=\s*", "", raw, flags=re.I)
            raw = raw.rstrip(";")
            try:
                payloads.append(json.loads(raw))
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
        for payload in self._parse_payloads(page):
            candidates.extend(
                walk_json_jobs(
                    payload=payload,
                    company_url=page.final_url,
                    requested_cities=requested_cities,
                    source_name="json-ssr",
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
