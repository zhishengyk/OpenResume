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


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


class BaseAlibabaCareerCollector(CompanyCollector):
    provider_cls: type | None = None
    page_limit_setting = ""
    page_size_setting = ""
    default_keyword = "\u524d\u7aef\u5de5\u7a0b\u5e08"

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
                    or [self.default_keyword]
                )
                if item.strip()
            )
        )
        if not keywords:
            keywords = [self.default_keyword]

        provider_cls = self.provider_cls
        if provider_cls is None:
            raise RuntimeError("Alibaba collector provider is not configured")

        provider = provider_cls(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, int(getattr(settings, self.page_limit_setting))),
            page_size=max(1, int(getattr(settings, self.page_size_setting))),
        )
        selected_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

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
        provider,
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
            "experienced": "\u793e\u62db",
            "campus": "\u6821\u62db",
            "internship": "\u5b9e\u4e60",
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
