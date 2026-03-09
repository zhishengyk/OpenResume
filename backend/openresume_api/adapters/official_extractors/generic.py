from __future__ import annotations

from ...services.official_sources import OfficialSource
from .base import ExtractedCandidate, FetchPage, OfficialExtractor
from .common import (
    build_detail_extraction,
    canonicalize_url,
    degree_text,
    experience_text,
    extract_city,
    extract_salary,
    find_anchor_blocks,
    hard_filter_reasons,
    looks_like_job,
    normalize_title,
    strip_html,
    work_mode,
)


class GenericExtractor(OfficialExtractor):
    name = "generic"

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        return True

    def extract_candidates(
        self,
        source: OfficialSource,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> list[ExtractedCandidate]:
        candidates: list[ExtractedCandidate] = []
        for href, label_html in find_anchor_blocks(page.text):
            detail_url = canonicalize_url(href, page.final_url)
            title = normalize_title(strip_html(label_html))
            if not detail_url or not title:
                continue
            snippet = title
            if not looks_like_job(title, snippet, requested_targets):
                continue
            salary_text, salary_min, salary_max = extract_salary(snippet)
            hard_reasons = hard_filter_reasons(title, detail_url, snippet, requested_targets)
            candidates.append(
                ExtractedCandidate(
                    title=title,
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
                        "source": "anchor",
                        "extractor": self.name,
                        "entry_url": page.final_url,
                        "href": href,
                        "seen_on": [detail_url],
                        "hard_filter_reasons": hard_reasons,
                    },
                )
            )
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
