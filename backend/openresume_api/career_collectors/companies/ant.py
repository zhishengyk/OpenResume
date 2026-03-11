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
from ..providers.ant_careers import AntCareerClient


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
DEFAULT_KEYWORD = "前端工程师"


class AntCollector(CompanyCollector):
    collector_key = "ant"

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

        provider = AntCareerClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_ant_page_limit),
            page_size=max(1, settings.official_ant_page_size),
            page_worker_count=max(1, settings.official_page_worker_count),
        )
        selected_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        jobs_with_ids = [
            item for item in selected_jobs if str(item.get("id") or "").strip()
        ]
        detail_by_job_id: dict[str, dict[str, Any]] = {}
        worker_count = min(settings.official_detail_worker_count, len(jobs_with_ids))
        job_ids = [str(item.get("id") or "").strip() for item in jobs_with_ids]
        detail_by_job_id = provider.get_job_details(
            variant=source.variant,
            job_ids=job_ids,
            worker_count=worker_count,
        )

        for item in jobs_with_ids:
            job_id = str(item.get("id") or "")
            merged = dict(item)
            merged.update(detail_by_job_id.get(job_id) or {})
            record = self._to_record(
                source,
                merged,
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
        provider: AntCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("id") or ""))
        title = normalize_whitespace(str(payload.get("name") or ""))
        if not job_id or not title:
            return None

        work_locations = payload.get("workLocations") or []
        if not isinstance(work_locations, list):
            work_locations = []
        location_values = [
            normalize_whitespace(str(item))
            for item in work_locations
            if str(item).strip()
        ]
        location_raw = " / ".join(location_values)
        location_city = normalize_city(location_values[0] if location_values else "")
        department = normalize_whitespace(
            str(payload.get("categoryName") or payload.get("department") or "")
        )
        description = normalize_multiline_text(str(payload.get("description") or ""))
        requirements = normalize_multiline_text(str(payload.get("requirement") or ""))

        return CollectedJobRecord(
            source_company=source.company_name,
            source_site=source.source_site,
            job_id=job_id,
            title=title,
            department=department,
            employment_type={
                "experienced": "社招",
                "campus": "校招",
                "internship": "实习",
            }.get(source.variant, ""),
            location_raw=location_raw,
            location_city=location_city,
            location_country="中国",
            remote_type="unknown",
            description_html=build_description_html(description, requirements),
            description_text=description,
            requirements_text=requirements,
            skills_extracted=[],
            posted_at=provider.parse_datetime(payload.get("publishTime")),
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
                "project": payload.get("project"),
                "category_name": payload.get("categoryName"),
                "batch_name": payload.get("batchName"),
                "batch_type": payload.get("batchType"),
                "experience": payload.get("experience"),
                "degree": payload.get("degree"),
                "tags": payload.get("tags"),
            },
        )


ant_collector = AntCollector()
