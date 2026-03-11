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
from ..providers.bilibili import BilibiliClient


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def _parse_datetime_text(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


class BilibiliCollector(CompanyCollector):
    collector_key = "bilibili"

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

        provider = BilibiliClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
            max_pages=max(1, settings.official_bilibili_page_limit),
            page_size=max(1, settings.official_bilibili_page_size),
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
        payload: dict[str, object],
        *,
        provider: BilibiliClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = str(payload.get("id") or "")
        title = normalize_whitespace(str(payload.get("positionName") or ""))
        if not job_id or not title:
            return None

        description = normalize_multiline_text(str(payload.get("positionDescription") or ""))
        location_raw = normalize_whitespace(str(payload.get("workLocation") or ""))
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(str(payload.get("postCodeName") or ""))
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
            description_html=build_description_html(description, ""),
            description_text=description,
            requirements_text="",
            skills_extracted=[],
            posted_at=_parse_datetime_text(payload.get("pushTime")),
            apply_url=provider.detail_url(variant=source.variant, job_id=job_id),
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "position_type_name": payload.get("positionTypeName"),
                "recruit_type": payload.get("recruitType"),
                "campus_project_id": payload.get("campusProjectId"),
                "hot_recruit": payload.get("hotRecruit"),
            },
        )


bilibili_collector = BilibiliCollector()
