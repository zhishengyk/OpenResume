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
from ..providers.meituan_official import MeituanOfficialClient


DEFAULT_KEYWORD = "\u524d\u7aef\u5f00\u53d1"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


class MeituanCollector(CompanyCollector):
    collector_key = "meituan"

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
                    or [DEFAULT_KEYWORD]
                )
                if item.strip()
            )
        )
        if not keywords:
            keywords = [DEFAULT_KEYWORD]

        provider = MeituanOfficialClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_meituan_page_limit),
            page_size=max(1, settings.official_meituan_page_size),
        )
        raw_jobs = provider.collect_jobs(variant=source.variant, keywords=keywords)
        selected_jobs = raw_jobs[: settings.official_job_limit_per_source]

        records: list[CollectedJobRecord] = []
        for item in selected_jobs:
            detail = provider.get_job_detail(
                variant=source.variant,
                job_id=str(item.get("jobUnionId") or ""),
            )
            merged = dict(item)
            merged.update(detail)
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
        provider: MeituanOfficialClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("jobUnionId") or ""))
        title = normalize_whitespace(str(payload.get("name") or ""))
        if not job_id or not title:
            return None

        city_list = payload.get("cityList") or []
        if not isinstance(city_list, list):
            city_list = []
        location_values = [
            normalize_whitespace(str(item.get("name") or ""))
            for item in city_list
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        location_raw = " / ".join(location_values)
        location_city = normalize_city(location_values[0] if location_values else "")

        departments = payload.get("department") or []
        if not isinstance(departments, list):
            departments = []
        department = " / ".join(
            normalize_whitespace(str(item.get("name") or ""))
            for item in departments
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        )

        description = normalize_multiline_text(str(payload.get("jobDuty") or ""))
        requirements = normalize_multiline_text(str(payload.get("jobRequirement") or ""))
        employment_type = {
            "campus": "\u6821\u62db",
            "internship": "\u5b9e\u4e60",
            "experienced": "\u793e\u62db",
        }.get(source.variant, "")

        return CollectedJobRecord(
            source_company=source.company_name,
            source_site=source.source_site,
            job_id=job_id,
            title=title,
            department=department,
            employment_type=employment_type,
            location_raw=location_raw,
            location_city=location_city,
            location_country="\u4e2d\u56fd",
            remote_type="unknown",
            description_html=build_description_html(description, requirements),
            description_text=description,
            requirements_text=requirements,
            skills_extracted=[],
            posted_at=epoch_millis_to_datetime(
                payload.get("firstPostTime") or payload.get("refreshTime")
            ),
            apply_url=provider.detail_url(variant=source.variant, job_id=job_id),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "job_family": payload.get("jobFamily"),
                "job_family_group": payload.get("jobFamilyGroup"),
                "job_type": payload.get("jobType"),
                "job_special_code": payload.get("jobSpecialCode"),
                "job_source": payload.get("jobSource"),
                "job_status": payload.get("jobStatus"),
                "work_year": payload.get("workYear"),
                "high_light": payload.get("highLight"),
                "department_intro": payload.get("departmentIntro"),
                "social_recommend_job": payload.get("socialRecommendJob"),
            },
        )


meituan_collector = MeituanCollector()
