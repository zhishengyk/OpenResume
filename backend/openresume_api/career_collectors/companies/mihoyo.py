from __future__ import annotations

from datetime import datetime

from ...config import settings
from ..base import CareerSiteSource, CollectedJobRecord, CompanyCollector
from ..normalization import (
    build_description_html,
    normalize_city,
    normalize_multiline_text,
    normalize_whitespace,
)
from ..providers.mihoyo_jobs import MihoyoJobsClient


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


class MihoyoCollector(CompanyCollector):
    collector_key = "mihoyo"

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

        provider = MihoyoJobsClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_mihoyo_page_limit),
            page_size=max(1, settings.official_mihoyo_page_size),
        )
        raw_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        for item in raw_jobs:
            detail = provider.fetch_detail(variant=source.variant, job_id=str(item.get("id") or ""))
            record = self._to_record(
                source,
                item,
                detail=detail,
                provider=provider,
                crawl_time=now,
            )
            if record is not None:
                records.append(record)
        return records

    def _to_record(
        self,
        source: CareerSiteSource,
        payload: dict[str, object],
        *,
        detail: dict[str, object],
        provider: MihoyoJobsClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = str(payload.get("id") or detail.get("id") or "")
        title = normalize_whitespace(
            str(detail.get("title") or payload.get("title") or "")
        )
        if not job_id or not title:
            return None

        address_details = detail.get("addressDetailList") or payload.get("addressDetailList") or []
        if not isinstance(address_details, list):
            address_details = []
        location_values = [
            normalize_whitespace(str(item.get("addressDetail") or ""))
            for item in address_details
            if isinstance(item, dict) and str(item.get("addressDetail") or "").strip()
        ]
        location_raw = " / ".join(location_values)
        location_city = normalize_city(location_values[0] if location_values else "")
        description = normalize_multiline_text(str(detail.get("description") or ""))
        requirements_parts = [
            normalize_multiline_text(str(detail.get("jobRequire") or "")),
            normalize_multiline_text(str(detail.get("addition") or "")),
        ]
        requirements = "\n".join(part for part in requirements_parts if part)
        department = normalize_whitespace(
            str(detail.get("competencyType") or payload.get("competencyType") or "")
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
            posted_at=None,
            apply_url=provider.detail_url(variant=source.variant, job_id=job_id),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "job_nature": detail.get("jobNature") or payload.get("jobNature"),
                "job_nature_id": detail.get("jobNatureId") or payload.get("jobNatureId"),
                "project_name": detail.get("projectName") or payload.get("projectName"),
                "object_name": detail.get("objectName") or payload.get("objectName"),
                "hurry": detail.get("hurry") or payload.get("hurry"),
            },
        )


mihoyo_collector = MihoyoCollector()
