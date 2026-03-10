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
from ..providers.tencent_career import TencentCareerClient, parse_tencent_date


class TencentCollector(CompanyCollector):
    collector_key = "tencent"

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
                for item in (
                    search.job_targets
                    or profile.target_roles
                    or ["前端工程师"]
                )
                if item.strip()
            )
        )
        if not keywords:
            keywords = ["前端工程师"]

        provider = TencentCareerClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            max_pages=max(1, settings.official_tencent_page_limit),
            page_size=max(1, settings.official_tencent_page_size),
        )
        raw_jobs = provider.collect_jobs(variant=source.variant, keywords=keywords)
        selected_jobs = raw_jobs[: settings.official_job_limit_per_source]

        records: list[CollectedJobRecord] = []
        for item in selected_jobs:
            record = self._to_record(source, item, provider=provider, crawl_time=now)
            if record is not None:
                records.append(record)
        return records

    def _to_record(
        self,
        source: CareerSiteSource,
        payload: dict[str, Any],
        *,
        provider: TencentCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("PostId") or ""))
        title = normalize_whitespace(str(payload.get("RecruitPostName") or ""))
        if not job_id or not title:
            return None

        description = normalize_multiline_text(str(payload.get("Responsibility") or ""))
        requirements = ""
        location_raw = normalize_whitespace(str(payload.get("LocationName") or ""))
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            str(payload.get("CategoryName") or payload.get("BGName") or "")
        )
        employment_type = {
            "experienced": "社招",
            "campus": "校招",
            "internship": "实习",
        }.get(source.variant, "")
        location_country = normalize_whitespace(str(payload.get("CountryName") or "中国"))
        apply_url = normalize_whitespace(str(payload.get("PostURL") or ""))
        if not apply_url:
            apply_url = provider.detail_url(job_id=job_id)

        return CollectedJobRecord(
            source_company="腾讯",
            source_site=source.source_site,
            job_id=job_id,
            title=title,
            department=department,
            employment_type=employment_type,
            location_raw=location_raw,
            location_city=location_city,
            location_country=location_country,
            remote_type="unknown",
            description_html=build_description_html(description, requirements),
            description_text=description,
            requirements_text=requirements,
            skills_extracted=[],
            posted_at=parse_tencent_date(payload.get("LastUpdateTime")),
            apply_url=apply_url,
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "recruit_post_id": payload.get("RecruitPostId"),
                "bg_name": payload.get("BGName"),
                "category_name": payload.get("CategoryName"),
                "last_update_time": payload.get("LastUpdateTime"),
            },
        )


tencent_collector = TencentCollector()
