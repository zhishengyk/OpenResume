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
from ..providers.bytedance_atsx import BytedanceAtsxClient


def _first_nested_name(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("name", "i18n_name", "en_name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


class BytedanceCollector(CompanyCollector):
    collector_key = "bytedance"

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
                    or ["\u524d\u7aef\u5de5\u7a0b\u5e08"]
                )
                if item.strip()
            )
        )
        if not keywords:
            keywords = ["\u524d\u7aef\u5de5\u7a0b\u5e08"]

        provider = BytedanceAtsxClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            max_pages=max(1, settings.official_bytedance_page_limit),
            page_size=max(1, settings.official_bytedance_page_size),
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
        provider: BytedanceAtsxClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = str(payload.get("id") or "")
        title = normalize_whitespace(str(payload.get("title") or ""))
        if not job_id or not title:
            return None

        description = normalize_multiline_text(str(payload.get("description") or ""))
        requirements = normalize_multiline_text(str(payload.get("requirement") or ""))
        city_info = payload.get("city_info") or {}
        location_raw = normalize_whitespace(
            _first_nested_name(city_info) or str(payload.get("location") or "")
        )
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            _first_nested_name(payload.get("job_category"))
            or _first_nested_name(payload.get("job_function"))
            or _first_nested_name(payload.get("job_subject"))
            or _first_nested_name(payload.get("department_info"))
        )
        employment_type = (
            "\u793e\u62db" if source.variant == "experienced" else "\u6821\u62db"
        )
        if not employment_type:
            employment_type = normalize_whitespace(
                _first_nested_name(payload.get("recruit_type"))
            )

        return CollectedJobRecord(
            source_company="\u5b57\u8282\u8df3\u52a8",
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
            posted_at=epoch_millis_to_datetime(payload.get("publish_time")),
            apply_url=provider.detail_url(variant=source.variant, job_id=job_id),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "publish_time": payload.get("publish_time"),
                "job_category": payload.get("job_category"),
                "job_function": payload.get("job_function"),
                "city_info": payload.get("city_info"),
            },
        )


bytedance_collector = BytedanceCollector()
