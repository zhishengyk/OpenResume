from __future__ import annotations

from datetime import datetime
import html as html_lib
import re
from typing import Any

from ...config import settings
from ..base import CareerSiteSource, CollectedJobRecord, CompanyCollector
from ..normalization import (
    build_description_html,
    normalize_city,
    normalize_multiline_text,
    normalize_whitespace,
)
from ..providers.ctrip_careers import CtripCareerClient, parse_ctrip_date


DEFAULT_KEYWORD = "\u524d\u7aef\u5f00\u53d1"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def _employment_type_label(variant: str) -> str:
    return {
        "experienced": "\u793e\u62db",
        "campus": "\u6821\u62db",
        "internship": "\u5b9e\u4e60",
    }.get(variant, "")


def _html_to_text(value: str) -> str:
    unescaped = html_lib.unescape(value or "")
    with_breaks = _TAG_PATTERN.sub("\n", unescaped)
    return normalize_multiline_text(with_breaks)


class CtripCollector(CompanyCollector):
    collector_key = "ctrip"

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

        provider = CtripCareerClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_ctrip_page_limit),
            page_size=max(1, settings.official_ctrip_page_size),
        )
        selected_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        for item in selected_jobs:
            payload = dict(item)
            from_id = normalize_whitespace(str(payload.get("fromId") or ""))
            if from_id:
                detail = provider.get_job_detail(job_id=from_id)
                payload.update(detail)

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
        provider: CtripCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("fromId") or payload.get("id") or ""))
        title = normalize_whitespace(str(payload.get("jobTitle") or ""))
        if not job_id or not title:
            return None

        location_raw = normalize_whitespace(str(payload.get("cityName") or payload.get("city") or ""))
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            str(payload.get("jobFamilyGroupName") or payload.get("buName") or "")
        )

        description = normalize_multiline_text(str(payload.get("duty") or ""))
        requirements = _html_to_text(str(payload.get("requirements") or ""))
        if not description and requirements:
            description = requirements
            requirements = ""

        detail_job_id = normalize_whitespace(str(payload.get("jobId") or job_id))

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
            posted_at=parse_ctrip_date(payload.get("publishDate")),
            apply_url=provider.detail_url(variant=source.variant, job_id=detail_job_id),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "job_id": payload.get("jobId"),
                "kind": payload.get("kind"),
                "kind_name": payload.get("kindName"),
                "category": payload.get("category"),
                "job_family_group_code": payload.get("jobFamilyGroupCode"),
                "bu_code": payload.get("buCode"),
                "channel_id": payload.get("channelId"),
                "ats_api_type": payload.get("atsApiType"),
            },
        )


ctrip_collector = CtripCollector()
