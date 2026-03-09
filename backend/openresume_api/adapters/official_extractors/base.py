from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from ...services.official_sources import OfficialSource


@dataclass
class FetchPage:
    requested_url: str
    final_url: str
    text: str
    status_code: int
    content_type: str


@dataclass
class ExtractedCandidate:
    title: str
    detail_url: str
    apply_url: str | None
    snippet: str
    company_url: str
    city: str
    salary_text: str
    salary_min: int
    salary_max: int
    experience_text: str
    degree_text: str
    work_mode: str
    department: str = ""
    location_text: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetailExtraction:
    fetched_url: str
    html: str
    text: str
    classification: str
    responsibilities: str
    requirements: str
    location_text: str
    department: str
    degree_text: str
    experience_text: str
    apply_url: str | None
    section_payload: dict[str, Any] = field(default_factory=dict)


class OfficialExtractor:
    name = "base"

    async def prepare_source_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        page: FetchPage,
    ) -> FetchPage:
        return page

    async def prepare_detail_page(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        candidate: ExtractedCandidate,
        page: FetchPage,
    ) -> FetchPage:
        return page

    def matches(self, source: OfficialSource, page: FetchPage) -> bool:
        return False

    def extract_candidates(
        self,
        source: OfficialSource,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> list[ExtractedCandidate]:
        raise NotImplementedError

    def extract_detail(
        self,
        source: OfficialSource,
        candidate: ExtractedCandidate,
        page: FetchPage,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> DetailExtraction:
        raise NotImplementedError
