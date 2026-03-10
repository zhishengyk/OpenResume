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
from ..providers.tencent_career import TencentCareerClient, parse_tencent_date
from ..providers.tencent_joinqq import JOINQQ_BASE_URL, TencentJoinQQClient


USER_AGENT = (
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


class TencentCollector(CompanyCollector):
    collector_key = "tencent"

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

        careers_provider = TencentCareerClient(
            timeout_seconds=settings.official_request_timeout_seconds,
            user_agent=USER_AGENT,
            max_pages=max(1, settings.official_tencent_page_limit),
            page_size=max(1, settings.official_tencent_page_size),
        )

        raw_jobs: list[dict[str, Any]] = careers_provider.collect_jobs(
            variant=source.variant,
            keywords=keywords,
        )

        if source.variant in {"campus", "internship"}:
            join_provider = TencentJoinQQClient(
                timeout_seconds=settings.official_request_timeout_seconds,
                user_agent=USER_AGENT,
                max_pages=max(1, settings.official_tencent_page_limit),
                page_size=max(1, settings.official_tencent_page_size),
            )
            raw_jobs.extend(join_provider.collect_jobs(variant=source.variant, keywords=keywords))

        selected_jobs = raw_jobs[: settings.official_job_limit_per_source]
        records: list[CollectedJobRecord] = []
        for item in selected_jobs:
            record = self._to_record(
                source,
                item,
                careers_provider=careers_provider,
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
        careers_provider: TencentCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        if "postId" in payload or "positionTitle" in payload:
            return self._to_joinqq_record(source, payload, crawl_time=crawl_time)
        return self._to_careers_record(
            source,
            payload,
            careers_provider=careers_provider,
            crawl_time=crawl_time,
        )

    def _to_careers_record(
        self,
        source: CareerSiteSource,
        payload: dict[str, Any],
        *,
        careers_provider: TencentCareerClient,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        job_id = normalize_whitespace(str(payload.get("PostId") or ""))
        title = normalize_whitespace(str(payload.get("RecruitPostName") or ""))
        if not job_id or not title:
            return None

        description = normalize_multiline_text(str(payload.get("Responsibility") or ""))
        requirements = ""
        location_raw = normalize_whitespace(str(payload.get("LocationName") or ""))
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            str(payload.get("CategoryName") or payload.get("BGName") or "")
        )
        location_country = normalize_whitespace(str(payload.get("CountryName") or "\u4e2d\u56fd"))
        apply_url = normalize_whitespace(str(payload.get("PostURL") or ""))
        if not apply_url:
            apply_url = careers_provider.detail_url(job_id=job_id)

        return CollectedJobRecord(
            source_company="\u817e\u8baf",
            source_site=normalize_whitespace(
                str(payload.get("__source_site") or source.source_site)
            ),
            job_id=job_id,
            title=title,
            department=department,
            employment_type=_employment_type_label(source.variant),
            location_raw=location_raw,
            location_city=location_city,
            location_country=location_country,
            remote_type="unknown",
            description_html=build_description_html(description, requirements),
            description_text=description,
            requirements_text=requirements,
            skills_extracted=[],
            posted_at=parse_tencent_date(payload.get("LastUpdateTime")),
            apply_url=apply_url,
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "recruit_post_id": payload.get("RecruitPostId"),
                "bg_name": payload.get("BGName"),
                "category_name": payload.get("CategoryName"),
                "last_update_time": payload.get("LastUpdateTime"),
            },
        )

    def _to_joinqq_record(
        self,
        source: CareerSiteSource,
        payload: dict[str, Any],
        *,
        crawl_time: datetime,
    ) -> CollectedJobRecord | None:
        post_id = normalize_whitespace(str(payload.get("postId") or payload.get("id") or ""))
        title = normalize_whitespace(str(payload.get("positionTitle") or payload.get("title") or ""))
        if not post_id or not title:
            return None

        description = normalize_multiline_text(
            str(payload.get("desc") or payload.get("introduction") or "")
        )
        requirements = normalize_multiline_text(str(payload.get("request") or ""))
        location_raw = normalize_whitespace(
            str(payload.get("workCities") or payload.get("workCity") or "")
        )
        location_city = normalize_city(location_raw)
        department = normalize_whitespace(
            str(payload.get("bgs") or payload.get("projectName") or "")
        )
        apply_url = normalize_whitespace(str(payload.get("positionUrl") or ""))
        if apply_url and not apply_url.startswith(("http://", "https://")):
            apply_url = f"{JOINQQ_BASE_URL}/{apply_url.lstrip('/')}"
        if not apply_url:
            apply_url = f"{JOINQQ_BASE_URL}/post_detail.html?postid={post_id}"

        return CollectedJobRecord(
            source_company="\u817e\u8baf",
            source_site=normalize_whitespace(
                str(payload.get("__source_site") or "join.qq.com")
            ),
            job_id=post_id,
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
            posted_at=None,
            apply_url=apply_url,
            salary_raw="",
            salary_min=None,
            salary_max=None,
            lang="zh-CN",
            crawl_time=crawl_time,
            raw_payload={
                "source_variant": source.variant,
                "project_id": payload.get("projectId"),
                "project_name": payload.get("projectName"),
                "recruit_label_name": payload.get("recruitLabelName"),
                "position_source": payload.get("positionSource"),
                "position_family": payload.get("positionFamily"),
            },
        )


tencent_collector = TencentCollector()
