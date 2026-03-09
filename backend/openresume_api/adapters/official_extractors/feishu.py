from __future__ import annotations

import json
import re

from ...services.official_sources import OfficialSource
from .base import ExtractedCandidate, FetchPage, OfficialExtractor
from .common import (
    build_detail_extraction,
    canonicalize_url,
    degree_text,
    experience_text,
    extract_city,
    extract_salary,
    find_script_blocks,
    hard_filter_reasons,
    normalize_title,
    strip_html,
    walk_json_jobs,
    work_mode,
)


class FeishuExtractor(OfficialExtractor):
    name = "feishu"

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        lowered = f"{source.url} {page.final_url} {page.text[:8000]}".lower()
        return (
            "jobs.feishu.cn" in lowered
            or "atsx" in lowered
            or "js-websiteinfo" in lowered
            or "/position/list" in lowered
        )

    def _website_payload(self, page: FetchPage) -> object | None:
        for block in find_script_blocks(page.text):
            if (block.get("id") or "").lower() != "js-websiteinfo":
                continue
            try:
                return json.loads(block.get("content") or "{}")
            except Exception:
                return None
        return None

    def _route_candidates(
        self,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> list[ExtractedCandidate]:
        candidates: list[ExtractedCandidate] = []
        pattern = re.compile(
            r'(?:"title"|name)\s*:\s*"([^"]+)"[^{}]{0,400}?(?:url|path|website_path)\s*:\s*"([^"]+/position/\d+/detail[^"]*)"',
            re.I,
        )
        for title, url in pattern.findall(page.text):
            detail_url = canonicalize_url(url, page.final_url)
            if not detail_url:
                continue
            snippet = normalize_title(title)
            salary_text, salary_min, salary_max = extract_salary(snippet)
            candidates.append(
                ExtractedCandidate(
                    title=normalize_title(title),
                    detail_url=detail_url,
                    apply_url=detail_url,
                    snippet=snippet,
                    company_url=page.final_url,
                    city=extract_city(snippet, requested_cities),
                    salary_text=salary_text,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    experience_text=experience_text(snippet),
                    degree_text=degree_text(snippet),
                    work_mode=work_mode(snippet),
                    raw_payload={
                        "source": "feishu-route",
                        "extractor": self.name,
                        "entry_url": page.final_url,
                        "seen_on": [detail_url],
                        "hard_filter_reasons": hard_filter_reasons(
                            title,
                            detail_url,
                            snippet,
                            requested_targets,
                        ),
                    },
                )
            )
        return candidates

    def extract_candidates(
        self,
        source: OfficialSource,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> list[ExtractedCandidate]:
        candidates: list[ExtractedCandidate] = []
        payload = self._website_payload(page)
        if payload is not None:
            candidates.extend(
                walk_json_jobs(
                    payload=payload,
                    company_url=page.final_url,
                    requested_cities=requested_cities,
                    source_name="feishu-json",
                )
            )
        candidates.extend(self._route_candidates(page, requested_targets, requested_cities))
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
        detail = build_detail_extraction(candidate, page, requested_targets, requested_cities)
        if not detail.apply_url:
            detail.apply_url = canonicalize_url(candidate.detail_url, page.final_url)
        return detail
