from __future__ import annotations

from datetime import datetime
from typing import Any

from ...config import settings
from ..base import CareerSiteSource, CollectedJobRecord, CompanyCollector
from ..normalization import (
    build_description_html,
    normalize_city,
    normalize_multiline_text,
    normalize_whitespace,
)
from ..providers.baidu_jobs import BaiduJobClient, parse_baidu_date


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


class BaiduCollector(CompanyCollector):
    collector_key = "baidu"

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

        provider = BaiduJobClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_baidu_page_limit),
            page_size=max(1, settings.official_baidu_page_size),
        )
        selected_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        for item in selected_jobs:
            record = self._to_record(
                source,
                item,
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
        provider: BaiduJobClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(
            str(payload.get("postId") or payload.get("jobId") or payload.get("id") or "")
        )
        title = normalize_whitespace(str(payload.get("name") or ""))
        if not job_id or not title:
            return None

        description = normalize_multiline_text(str(payload.get("workContent") or ""))
        requirements = normalize_multiline_text(str(payload.get("serviceCondition") or ""))
        location_raw = normalize_whitespace(str(payload.get("workPlace") or ""))
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            str(payload.get("postType") or payload.get("bgShortName") or "")
        )

        posted_at = parse_baidu_date(payload.get("updateDate")) or parse_baidu_date(
            payload.get("publishDate")
        )

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
                entry_url=str(payload.get("__entry_url") or ""),
            ),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "recruit_type": payload.get("__recruit_type"),
                "project_type": payload.get("projectType"),
                "project_type_code": payload.get("projectTypeCode"),
                "post_type": payload.get("postType"),
                "bg_short_name": payload.get("bgShortName"),
                "favorite_flag": payload.get("favoriteFlag"),
                "hot_flag": payload.get("hotFlag"),
                "recruit_num": payload.get("recruitNum"),
            },
        )


baidu_collector = BaiduCollector()
