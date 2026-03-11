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
from ..providers.kuaishou_campus import KuaishouCampusClient
from ..providers.kuaishou_social import KuaishouSocialClient


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
DEFAULT_KEYWORD = "前端工程师"


class KuaishouCollector(CompanyCollector):
    collector_key = "kuaishou"

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

        social_provider = KuaishouSocialClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_kuaishou_page_limit),
            page_size=max(1, settings.official_kuaishou_page_size),
        )
        campus_provider = KuaishouCampusClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_kuaishou_page_limit),
            page_size=max(1, settings.official_kuaishou_page_size),
        )

        if source.variant == "experienced":
            raw_jobs = social_provider.collect_jobs(variant="experienced", keywords=keywords)
        elif source.variant == "campus":
            raw_jobs = campus_provider.collect_jobs(variant="campus", keywords=keywords)
        else:
            # Internship is split across campus and social channels.
            raw_jobs = campus_provider.collect_jobs(variant="internship", keywords=keywords)
            raw_jobs.extend(
                social_provider.collect_jobs(variant="internship", keywords=keywords)
            )

        selected_jobs = raw_jobs[: settings.official_job_limit_per_source]
        records: list[CollectedJobRecord] = []
        seen_job_ids: set[str] = set()

        for item in selected_jobs:
            job_id = normalize_whitespace(str(item.get("id") or ""))
            if not job_id or job_id in seen_job_ids:
                continue
            seen_job_ids.add(job_id)

            payload = dict(item)
            if (
                source.variant in {"campus", "internship"}
                and str(payload.get("__source_channel") or "") == "campus"
                and not str(payload.get("description") or "").strip()
            ):
                detail = campus_provider.get_job_detail(job_id=job_id)
                payload.update(detail)

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
        social_provider: KuaishouSocialClient,
        campus_provider: KuaishouCampusClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("id") or ""))
        title = normalize_whitespace(str(payload.get("name") or ""))
        if not job_id or not title:
            return None

        locations = payload.get("workLocations") or []
        if not isinstance(locations, list):
            locations = []
        location_values = [
            normalize_whitespace(str(item))
            for item in locations
            if str(item).strip()
        ]
        location_raw = normalize_whitespace(
            " / ".join(location_values)
            or str(payload.get("workLocationName") or "")
            or str(payload.get("workLocationCode") or "")
        )
        location_city = normalize_city(location_values[0] if location_values else location_raw)
        department = normalize_whitespace(
            str(
                payload.get("departmentName")
                or payload.get("businessDirectory")
                or payload.get("positionCategoryCode")
                or ""
            )
        )
        description = normalize_multiline_text(str(payload.get("description") or ""))
        requirements = normalize_multiline_text(
            str(payload.get("positionDemand") or payload.get("requirement") or "")
        )
        source_channel = normalize_whitespace(str(payload.get("__source_channel") or "social"))

        if source_channel == "campus":
            apply_url = campus_provider.detail_url(
                variant=source.variant,
                job_id=job_id,
                position_code=normalize_whitespace(str(payload.get("code") or "")),
            )
        else:
            apply_url = social_provider.detail_url(job_id=job_id)

        salary_min = _to_int(payload.get("salaryMin"))
        salary_max = _to_int(payload.get("salaryMax"))
        salary_raw = ""
        if salary_min is not None and salary_max is not None:
            salary_raw = f"{salary_min}-{salary_max}"

        posted_at = (
            epoch_millis_to_datetime(payload.get("updateTime"))
            or epoch_millis_to_datetime(payload.get("createTime"))
            or epoch_millis_to_datetime(payload.get("releaseTime"))
        )

        return CollectedJobRecord(
            source_company=source.company_name,
            source_site=normalize_whitespace(
                str(payload.get("__source_site") or source.source_site)
            ),
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
            posted_at=posted_at,
            apply_url=apply_url,
            salary_raw=salary_raw,
            salary_min=salary_min,
            salary_max=salary_max,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_channel": source_channel,
                "position_nature_code": payload.get("positionNatureCode"),
                "recruit_project_code": payload.get("recruitProjectCode"),
                "work_experience_code": payload.get("workExperienceCode"),
                "education_limit_code": payload.get("educationLimitCode"),
                "recruit_start_date": payload.get("recruitStartDate"),
                "recruit_end_date": payload.get("recruitEndDate"),
                "position_status_code": payload.get("positionStatusCode"),
            },
        )


def _to_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


kuaishou_collector = KuaishouCollector()
