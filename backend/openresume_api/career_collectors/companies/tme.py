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
from ..providers.tme_careers import TmeCareerClient, parse_tme_date


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


class TmeCollector(CompanyCollector):
    collector_key = "tme"

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

        provider = TmeCareerClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_tme_page_limit),
            page_size=max(1, settings.official_tme_page_size),
        )
        selected_jobs = provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
            limit=self.source_job_limit(search),
        )

        records: list[CollectedJobRecord] = []
        for item in selected_jobs:
            payload = dict(item)
            job_id = normalize_whitespace(str(payload.get("id") or ""))
            if job_id:
                detail = provider.get_job_detail(variant=source.variant, job_id=job_id)
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
        provider: TmeCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("id") or ""))
        title = normalize_whitespace(str(payload.get("name") or ""))
        if not job_id or not title:
            return None

        location_raw = self._extract_location(payload)
        location_city = normalize_city(location_raw)
        description = normalize_multiline_text(str(payload.get("duty") or ""))
        requirements = normalize_multiline_text(str(payload.get("requirement") or ""))
        department = normalize_whitespace(
            str(payload.get("jobf_descr") or payload.get("company_set") or "")
        )

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
            posted_at=parse_tme_date(payload.get("date")),
            apply_url=provider.detail_url(variant=source.variant, job_id=job_id),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "position_nbr": payload.get("position_nbr"),
                "position_nbr_descr": payload.get("position_nbr_descr"),
                "work_nature_descr": payload.get("work_nature_descr"),
                "job_type": payload.get("job_type"),
                "job_type_descr": payload.get("job_type_descr"),
                "setid": payload.get("setid"),
                "setid_descr": payload.get("setid_descr"),
                "need_num": payload.get("need_num"),
            },
        )

    def _extract_location(self, payload: dict[str, Any]) -> str:
        work_city = payload.get("work_city")
        if isinstance(work_city, str):
            return normalize_whitespace(work_city)
        if isinstance(work_city, list):
            values = []
            for item in work_city:
                if isinstance(item, dict):
                    label = normalize_whitespace(str(item.get("label") or item.get("value") or ""))
                    if label:
                        values.append(label)
                else:
                    label = normalize_whitespace(str(item))
                    if label:
                        values.append(label)
            return " / ".join(values)
        return ""


tme_collector = TmeCollector()
