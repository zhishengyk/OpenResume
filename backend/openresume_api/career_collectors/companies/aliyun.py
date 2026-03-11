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
from ..providers.aliyun_careers import AliyunCareersClient


class AliyunCollector(CompanyCollector):
    collector_key = "aliyun"

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

        provider = AliyunCareersClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            max_pages=max(1, settings.official_aliyun_page_limit),
            page_size=max(1, settings.official_aliyun_page_size),
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
        provider: AliyunCareersClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = str(payload.get("id") or "")
        title = normalize_whitespace(str(payload.get("name") or ""))
        if not job_id or not title:
            return None

        description = normalize_multiline_text(str(payload.get("description") or ""))
        requirements = normalize_multiline_text(str(payload.get("requirement") or ""))
        work_locations = payload.get("workLocations") or []
        if not isinstance(work_locations, list):
            work_locations = []
        location_values = [
            normalize_whitespace(str(item)) for item in work_locations if str(item).strip()
        ]
        location_raw = " / ".join(location_values)
        location_city = normalize_city(location_values[0] if location_values else "")
        department = normalize_whitespace(
            str(
                payload.get("categoryName")
                or payload.get("department")
                or payload.get("project")
                or ""
            )
        )
        employment_type = {
            "experienced": "社招",
            "campus": "校招",
            "internship": "实习",
        }.get(source.variant, "")

        return CollectedJobRecord(
            source_company="阿里云",
            source_site=source.source_site,
            job_id=job_id,
            title=title,
            department=department,
            employment_type=employment_type,
            location_raw=location_raw,
            location_city=location_city,
            location_country="中国",
            remote_type="unknown",
            description_html=build_description_html(description, requirements),
            description_text=description,
            requirements_text=requirements,
            skills_extracted=[],
            posted_at=epoch_millis_to_datetime(
                payload.get("publishTime") or payload.get("modifyTime")
            ),
            apply_url=provider.detail_url(
                variant=source.variant,
                job_id=job_id,
                position_url=str(payload.get("positionUrl") or ""),
            ),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "category_type": payload.get("categoryType"),
                "position_type": payload.get("positionType"),
                "degree": payload.get("degree"),
                "experience": payload.get("experience"),
                "modify_time": payload.get("modifyTime"),
                "publish_time": payload.get("publishTime"),
                "work_locations": payload.get("workLocations"),
                "batch_name": payload.get("batchName"),
                "department": payload.get("department"),
            },
        )


aliyun_collector = AliyunCollector()
