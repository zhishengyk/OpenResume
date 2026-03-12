from __future__ import annotations

from datetime import datetime
from typing import Any

from ...config import settings
from ..base import CareerSiteSource, CollectedJobRecord, CompanyCollector
from ..normalization import (
    build_description_html,
    epoch_millis_to_datetime,
    normalize_city,
    normalize_multiline_text,
    normalize_whitespace,
)
from ..providers.netease_careers import NeteaseCareerClient


DEFAULT_KEYWORD = "\u524d\u7aef\u5f00\u53d1"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def _employment_type_label(variant: str) -> str:
    return {
        "experienced": "\u793e\u62db",
        "campus": "\u6821\u62db",
        "internship": "\u5b9e\u4e60",
    }.get(variant, "")


class NeteaseCollector(CompanyCollector):
    collector_key = "netease"

    def collect(
        self,
        source: CareerSiteSource,
        search,
        profile,
        now: datetime,
    ) -> list[CollectedJobRecord]:
        keywords = list(
            dict.fromkeys(
                item.strip()
                for item in (search.job_targets or profile.target_roles or [DEFAULT_KEYWORD])
                if item.strip()
            )
        )
        if not keywords:
            keywords = [DEFAULT_KEYWORD]

        provider = NeteaseCareerClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_netease_page_limit),
            page_size=max(1, settings.official_netease_page_size),
        )
        selected_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        for payload in selected_jobs:
            record = self._to_record(
                source,
                payload,
                provider=provider,
                crawl_time=now,
            )
            if record is not None:
                records.append(record)
        return records

    def _to_record(
        self,
        source: CareerSiteSource,
        payload: dict[str, Any],
        *,
        provider: NeteaseCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("id") or ""))
        title = normalize_whitespace(str(payload.get("name") or payload.get("positionName") or ""))
        if not job_id or not title:
            return None

        location_raw = self._extract_location(payload)
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            str(payload.get("firstDepName") or payload.get("positionTypeName") or "")
        )
        description = normalize_multiline_text(
            str(payload.get("description") or payload.get("positionDescription") or "")
        )
        requirements = normalize_multiline_text(
            str(payload.get("requirement") or payload.get("positionRequirement") or "")
        )

        posted_at = epoch_millis_to_datetime(payload.get("updateTime"))
        project_id = payload.get("__project_id") or payload.get("projectId")

        return CollectedJobRecord(
            source_company=source.company_name,
            source_site=normalize_whitespace(
                str(payload.get("__source_site") or source.source_site)
            ),
            job_id=job_id,
            title=title,
            department=department,
            employment_type=_employment_type_label(source.variant),
            location_raw=location_raw,
            location_city=location_city,
            location_country="\u4e2d\u56fd",
            remote_type="unknown",
            description_html=build_description_html(description, requirements),
            description_text=description,
            requirements_text=requirements,
            skills_extracted=[],
            posted_at=posted_at,
            apply_url=provider.detail_url(
                variant=source.variant,
                job_id=job_id,
                bee_url=str(payload.get("beeUrl") or ""),
                project_id=project_id,
            ),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "work_type": payload.get("workType"),
                "education": payload.get("reqEducationName"),
                "work_years": payload.get("reqWorkYearsName"),
                "product_name": payload.get("productName"),
                "interview_city_name": payload.get("interviewCityName"),
                "is_hot": payload.get("isHot"),
                "project_id": project_id,
            },
        )

    def _extract_location(self, payload: dict[str, Any]) -> str:
        work_place_name_list = payload.get("workPlaceNameList")
        if isinstance(work_place_name_list, list):
            values = [normalize_whitespace(str(item)) for item in work_place_name_list if str(item).strip()]
            if values:
                return " / ".join(values)
        return normalize_whitespace(str(payload.get("workPlaceName") or ""))


netease_collector = NeteaseCollector()
