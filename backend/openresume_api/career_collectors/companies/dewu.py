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
from ..providers.dewu_feishu import DewuFeishuClient


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def _first_nested_name(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("name", "i18n_name", "en_name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


class DewuCollector(CompanyCollector):
    collector_key = "dewu"

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
                for item in (search.job_targets or profile.target_roles or ["前端工程师"])
                if item.strip()
            )
        )
        if not keywords:
            keywords = ["前端工程师"]

        provider = DewuFeishuClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_dewu_page_limit),
            page_size=max(1, settings.official_dewu_page_size),
        )
        raw_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        for item in raw_jobs:
            record = self._to_record(source, item, provider=provider, crawl_time=now)
            if record is not None:
                records.append(record)
        return records

    def _to_record(
        self,
        source: CareerSiteSource,
        payload: dict[str, Any],
        *,
        provider: DewuFeishuClient,
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
            _first_nested_name(city_info)
            or " / ".join(
                normalize_whitespace(str(item.get("name") or ""))
                for item in (payload.get("city_list") or [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            )
        )
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            _first_nested_name(payload.get("job_category"))
            or _first_nested_name(payload.get("job_function"))
            or _first_nested_name(payload.get("job_subject"))
        )
        employment_type = {
            "experienced": "社招",
            "campus": "校招",
            "internship": "实习",
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
            location_country="中国",
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
                "recruit_type": payload.get("recruit_type"),
                "job_category": payload.get("job_category"),
                "job_function": payload.get("job_function"),
                "job_subject": payload.get("job_subject"),
            },
        )


dewu_collector = DewuCollector()
