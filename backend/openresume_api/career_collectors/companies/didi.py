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
from ..providers.didi_careers import DidiCareerClient, parse_didi_datetime


DEFAULT_KEYWORD = "\u524d\u7aef\u5f00\u53d1"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def _employment_type_label(variant: str) -> str:
    return {
        "experienced": "\u793e\u62db",
        "campus": "\u6821\u62db",
        "internship": "\u5b9e\u4e60",
    }.get(variant, "")


class DidiCollector(CompanyCollector):
    collector_key = "didi"

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

        provider = DidiCareerClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_didi_page_limit),
            page_size=max(1, settings.official_didi_page_size),
        )
        selected_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        for item in selected_jobs:
            payload = dict(item)
            if source.variant == "experienced":
                job_id = normalize_whitespace(str(payload.get("jdId") or payload.get("id") or ""))
                if job_id:
                    detail = provider.get_social_job_detail(job_id=job_id)
                    payload.update(detail)

            record = self._to_record(
                source,
                payload,
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
        provider: DidiCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("jdId") or payload.get("id") or ""))
        title = normalize_whitespace(str(payload.get("jobName") or payload.get("title") or ""))
        if not job_id or not title:
            return None

        location_raw = self._extract_location(payload)
        location_city = normalize_city(location_raw)
        description = normalize_multiline_text(str(payload.get("jobDesc") or ""))
        requirements = normalize_multiline_text(str(payload.get("qualification") or ""))
        department = normalize_whitespace(
            str(payload.get("deptName") or (payload.get("department") or {}).get("name") or "")
        )
        posted_at = (
            parse_didi_datetime(payload.get("publishTime"))
            or parse_didi_datetime(payload.get("publishedAt"))
            or parse_didi_datetime(payload.get("refreshTime"))
            or parse_didi_datetime(payload.get("updatedAt"))
            or parse_didi_datetime(payload.get("createdAt"))
        )

        if source.variant == "experienced":
            apply_url = provider.social_detail_url(job_id=job_id)
        else:
            apply_url = provider.campus_apply_url(payload)

        return CollectedJobRecord(
            source_company=source.company_name,
            source_site=normalize_whitespace(
                str(payload.get("__source_site") or source.source_site)
            ),
            job_id=job_id,
            title=title,
            department=department,
            employment_type=_employment_type_label(source.variant),
            location_raw=location_raw,
            location_city=location_city,
            location_country="\u4e2d\u56fd",
            remote_type="unknown",
            description_html=build_description_html(description, requirements),
            description_text=description,
            requirements_text=requirements,
            skills_extracted=[],
            posted_at=posted_at,
            apply_url=apply_url,
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "jd_no": payload.get("jdNo"),
                "job_type": payload.get("jobType"),
                "label_code": payload.get("labelCode"),
                "recruit_type": payload.get("recruitType"),
                "recruit_num": payload.get("recruitNum"),
                "status": payload.get("status") or payload.get("jdStatus"),
                "commitment": payload.get("commitment"),
                "education": payload.get("education"),
                "zhineng": (payload.get("zhineng") or {}).get("name"),
                "project": payload.get("projectName"),
            },
        )

    def _extract_location(self, payload: dict[str, Any]) -> str:
        location_raw = normalize_whitespace(str(payload.get("workArea") or ""))
        if location_raw:
            return location_raw

        location = payload.get("location") or {}
        if isinstance(location, dict):
            address = normalize_whitespace(str(location.get("address") or ""))
            if address:
                return address

        locations = payload.get("locations") or []
        if not isinstance(locations, list):
            locations = []
        values = []
        for item in locations:
            if not isinstance(item, dict):
                continue
            address = normalize_whitespace(str(item.get("address") or ""))
            if address:
                values.append(address)
        return " / ".join(values)


didi_collector = DidiCollector()
