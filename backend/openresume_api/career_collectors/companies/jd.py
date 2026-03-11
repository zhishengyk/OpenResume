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
from ..providers.jd_campus import JdCampusClient
from ..providers.jd_social import JdSocialClient


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
DEFAULT_KEYWORD = "前端工程师"


class JdCollector(CompanyCollector):
    collector_key = "jd"

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

        social_provider = JdSocialClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_jd_page_limit),
            page_size=max(1, settings.official_jd_page_size),
            page_worker_count=max(1, settings.official_page_worker_count),
        )
        campus_provider = JdCampusClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_jd_page_limit),
            page_size=max(1, settings.official_jd_page_size),
            page_worker_count=max(1, settings.official_page_worker_count),
        )

        if source.variant == "experienced":
            selected_jobs = social_provider.collect_jobs(
                keywords=keywords,
                limit=self.source_job_limit(search),
            )
        else:
            selected_jobs = campus_provider.collect_jobs(
                variant=source.variant,
                keywords=keywords,
                limit=self.source_job_limit(search),
            )
        records: list[CollectedJobRecord] = []

        detail_by_publish_id: dict[str, dict[str, Any]] = {}
        if source.variant in {"campus", "internship"}:
            jobs_with_publish_id = [
                item
                for item in selected_jobs
                if normalize_whitespace(str(item.get("publishId") or ""))
            ]
            worker_count = min(settings.official_detail_worker_count, len(jobs_with_publish_id))
            publish_ids = [
                normalize_whitespace(str(item.get("publishId") or ""))
                for item in jobs_with_publish_id
            ]
            detail_by_publish_id = campus_provider.get_job_details(
                variant=source.variant,
                publish_ids=publish_ids,
                worker_count=worker_count,
            )

        for item in selected_jobs:
            payload = dict(item)
            if source.variant in {"campus", "internship"}:
                publish_id = normalize_whitespace(str(payload.get("publishId") or ""))
                if publish_id:
                    payload.update(detail_by_publish_id.get(publish_id) or {})

            record = self._to_record(
                source,
                payload,
                social_provider=social_provider,
                campus_provider=campus_provider,
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
        social_provider: JdSocialClient,
        campus_provider: JdCampusClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(
            str(
                payload.get("requirementId")
                or payload.get("positionId")
                or payload.get("publishId")
                or payload.get("id")
                or ""
            )
        )
        title = normalize_whitespace(
            str(payload.get("positionNameOpen") or payload.get("positionName") or "")
        )
        if not job_id or not title:
            return None

        location_raw = normalize_whitespace(str(payload.get("workCity") or ""))
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            str(
                payload.get("positionDept")
                or payload.get("positionDeptName")
                or payload.get("positionTypeName")
                or payload.get("jobType")
                or payload.get("jobDirection")
                or ""
            )
        )
        description = normalize_multiline_text(str(payload.get("workContent") or ""))
        requirements = normalize_multiline_text(str(payload.get("qualification") or ""))

        if source.variant == "experienced":
            apply_url = social_provider.detail_url(job_id=job_id)
        else:
            apply_url = campus_provider.detail_url(
                variant=source.variant,
                publish_id=normalize_whitespace(str(payload.get("publishId") or "")),
            )

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
            posted_at=epoch_millis_to_datetime(payload.get("publishTime")),
            apply_url=apply_url,
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "plan_id": payload.get("planId"),
                "job_direction": payload.get("jobDirection"),
                "job_direction_code": payload.get("jobDirectionCode"),
                "job_category": payload.get("jobCategory"),
                "job_category_code": payload.get("jobCategoryCode"),
                "education": payload.get("education"),
                "work_years": payload.get("workYears"),
                "position_type": payload.get("positionType"),
                "position_type_name": payload.get("positionTypeName"),
                "position_code": payload.get("positionCode"),
                "req_number": payload.get("reqNumber"),
            },
        )


jd_collector = JdCollector()
