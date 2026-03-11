from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import hashlib
import json
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, delete, select

from .. import db as db_module
from ..adapters.base import NormalizedJobDraft, PlatformBlockedError
from ..models import (
    AppSetting,
    CandidateProfile,
    JobListing,
    JobMatch,
    SearchFetchCache,
    SearchSession,
)
from ..schemas import SearchSessionCreate
from .events import event_bus
from .llm import llm_service
from .matching import matching_service
from .platform_gateway import platform_gateway
from .profile import profile_service
from .risk import risk_control_service

LLM_ANALYSIS_LIMIT = 120
FETCH_CACHE_TTL_SECONDS = 60 * 60


class SearchService:
    def _session_meta_key(self, session_id: str) -> str:
        return f"search_session_meta:{session_id}"

    def _get_session_meta(self, db: Session, session_id: str) -> dict:
        setting = db.get(AppSetting, self._session_meta_key(session_id))
        return dict(setting.value or {}) if setting else {}

    def _set_session_meta(self, db: Session, session_id: str, **updates: object) -> dict:
        key = self._session_meta_key(session_id)
        setting = db.get(AppSetting, key)
        if not setting:
            setting = AppSetting(key=key, value={})
        setting.value = {
            **(setting.value or {}),
            **updates,
        }
        setting.updated_at = datetime.utcnow()
        db.add(setting)
        db.commit()
        db.refresh(setting)
        return dict(setting.value or {})

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _serialize_draft(draft: NormalizedJobDraft) -> dict[str, Any]:
        return {
            "source_company": draft.source_company,
            "source_site": draft.source_site,
            "job_id": draft.job_id,
            "title": draft.title,
            "department": draft.department,
            "employment_type": draft.employment_type,
            "location_raw": draft.location_raw,
            "location_city": draft.location_city,
            "location_country": draft.location_country,
            "remote_type": draft.remote_type,
            "description_html": draft.description_html,
            "description_text": draft.description_text,
            "requirements_text": draft.requirements_text,
            "skills_extracted": list(draft.skills_extracted),
            "posted_at": draft.posted_at.isoformat() if draft.posted_at else None,
            "apply_url": draft.apply_url,
            "salary_raw": draft.salary_raw,
            "salary_min": draft.salary_min,
            "salary_max": draft.salary_max,
            "lang": draft.lang,
            "crawl_time": draft.crawl_time.isoformat() if draft.crawl_time else None,
            "raw_payload": dict(draft.raw_payload or {}),
        }

    def _deserialize_drafts(self, payload_json: list[dict[str, Any]]) -> list[NormalizedJobDraft]:
        drafts: list[NormalizedJobDraft] = []
        for item in payload_json:
            drafts.append(
                NormalizedJobDraft(
                    source_company=str(item.get("source_company") or ""),
                    source_site=str(item.get("source_site") or ""),
                    job_id=str(item.get("job_id") or ""),
                    title=str(item.get("title") or ""),
                    department=str(item.get("department") or ""),
                    employment_type=str(item.get("employment_type") or ""),
                    location_raw=str(item.get("location_raw") or ""),
                    location_city=str(item.get("location_city") or ""),
                    location_country=str(item.get("location_country") or ""),
                    remote_type=str(item.get("remote_type") or "unknown"),
                    description_html=str(item.get("description_html") or ""),
                    description_text=str(item.get("description_text") or ""),
                    requirements_text=str(item.get("requirements_text") or ""),
                    skills_extracted=list(item.get("skills_extracted") or []),
                    posted_at=self._parse_dt(item.get("posted_at")),
                    apply_url=str(item.get("apply_url") or ""),
                    salary_raw=str(item.get("salary_raw") or ""),
                    salary_min=item.get("salary_min"),
                    salary_max=item.get("salary_max"),
                    lang=str(item.get("lang") or "zh-CN"),
                    crawl_time=self._parse_dt(item.get("crawl_time")),
                    raw_payload=dict(item.get("raw_payload") or {}),
                )
            )
        return drafts

    @staticmethod
    def _normalized_fetch_inputs(
        payload: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> dict[str, Any]:
        keywords = profile_service.build_search_keyword_basis(payload.job_targets, profile)
        identity = {
            "platforms": sorted(dict.fromkeys(payload.platforms)),
            "source_variants": sorted(dict.fromkeys(payload.source_variants or [])),
            "source_companies": sorted(dict.fromkeys(payload.source_companies or [])),
            "keyword_basis": sorted(dict.fromkeys(keywords)),
        }
        return identity

    @staticmethod
    def _fetch_cache_key(identity: dict[str, Any]) -> str:
        content = json.dumps(identity, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _payload_from_session(session: SearchSession) -> SearchSessionCreate:
        return SearchSessionCreate(
            platforms=list(session.requested_platforms or []),
            mode=session.mode,
            job_targets=list(session.job_targets or []),
            cities=list(session.cities or []),
            salary_floor=session.salary_floor,
            must_have_keywords=list(session.must_have_keywords or []),
            source_variants=list(session.source_variants or []),
            source_companies=list(session.source_companies or []),
            force_refresh=bool(session.force_refresh),
        )

    async def create_session(
        self,
        db: Session,
        payload: SearchSessionCreate,
    ) -> SearchSession:
        session = SearchSession(
            requested_platforms=payload.platforms,
            mode=payload.mode,
            status="running",
            job_targets=payload.job_targets,
            cities=payload.cities,
            salary_floor=payload.salary_floor,
            must_have_keywords=payload.must_have_keywords,
            source_variants=payload.source_variants,
            source_companies=payload.source_companies,
            force_refresh=payload.force_refresh,
            summary="搜索已开始，正在抓取并清洗官网职位。",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        self._set_session_meta(
            db,
            session.id,
            retry_count=0,
            retryable=False,
            verification_url=None,
            verification_title=None,
            verification_opened_at=None,
            blocked_at=None,
            last_retry_at=None,
        )
        event_bus.publish(session.id, "search_started", "搜索任务已创建。")
        asyncio.create_task(self._run_pipeline(session.id, payload))
        return session

    async def retry_session(self, db: Session, session_id: str) -> SearchSession:
        session = db.get(SearchSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="未找到搜索任务。")
        if session.status == "running":
            raise HTTPException(status_code=409, detail="搜索任务仍在运行中。")

        meta = self._get_session_meta(db, session_id)
        retry_count = int(meta.get("retry_count") or 0) + 1
        session.status = "running"
        session.blocked_reason = None
        session.summary = "正在重试本次搜索。"
        session.updated_at = datetime.utcnow()
        db.add(session)
        db.commit()
        db.refresh(session)

        self._set_session_meta(
            db,
            session_id,
            retry_count=retry_count,
            retryable=False,
            blocked_at=None,
            last_retry_at=datetime.utcnow().isoformat(),
        )
        event_bus.reset(session_id)
        event_bus.publish(
            session_id,
            "search_restarted",
            f"第 {retry_count} 次重试已开始。",
            {"retry_count": retry_count},
        )
        asyncio.create_task(self._run_pipeline(session.id, self._payload_from_session(session)))
        return session

    async def reopen_verification(self, db: Session, session_id: str) -> dict[str, str]:
        session = db.get(SearchSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="未找到搜索任务。")

        meta = self._get_session_meta(db, session_id)
        verification_url = meta.get("verification_url")
        if not verification_url:
            raise HTTPException(status_code=409, detail="当前搜索任务没有可重新打开的验证窗口。")

        self._set_session_meta(
            db,
            session_id,
            verification_opened_at=datetime.utcnow().isoformat(),
            retryable=True,
        )
        event_bus.publish(
            session_id,
            "verification_opened",
            "验证窗口已可在应用内重新打开。",
        )
        return {
            "url": str(verification_url),
            "title": str(meta.get("verification_title") or "搜索验证"),
            "message": "请打开验证窗口完成验证，然后再重试搜索。",
        }

    async def _fetch_platform_jobs(
        self,
        db: Session,
        payload: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> tuple[list[NormalizedJobDraft], bool]:
        now = datetime.utcnow()
        db.exec(delete(SearchFetchCache).where(SearchFetchCache.expires_at < now))
        db.commit()

        identity = self._normalized_fetch_inputs(payload, profile)
        cache_key = self._fetch_cache_key(identity)
        cached = db.get(SearchFetchCache, cache_key)
        if cached and not payload.force_refresh and cached.expires_at >= now:
            cached.hit_count += 1
            db.add(cached)
            db.commit()
            return self._deserialize_drafts(cached.payload_json), True

        drafts: list[NormalizedJobDraft] = []
        errors: list[str] = []
        for adapter in platform_gateway.resolve(payload.platforms):
            try:
                drafts.extend(await adapter.search_jobs(payload, profile))
            except PlatformBlockedError:
                raise
            except Exception as error:
                errors.append(f"{adapter.platform}: {error}")
        if drafts:
            fresh_now = datetime.utcnow()
            serialized = [self._serialize_draft(draft) for draft in drafts]
            source_filters = {
                "source_variants": list(identity["source_variants"]),
                "source_companies": list(identity["source_companies"]),
            }
            if cached:
                cached.platforms = list(identity["platforms"])
                cached.source_filters = source_filters
                cached.keyword_basis = list(identity["keyword_basis"])
                cached.payload_json = serialized
                cached.created_at = fresh_now
                cached.expires_at = fresh_now + timedelta(seconds=FETCH_CACHE_TTL_SECONDS)
                cached.hit_count = 0
                db.add(cached)
            else:
                db.add(
                    SearchFetchCache(
                        cache_key=cache_key,
                        platforms=list(identity["platforms"]),
                        source_filters=source_filters,
                        keyword_basis=list(identity["keyword_basis"]),
                        payload_json=serialized,
                        created_at=fresh_now,
                        expires_at=fresh_now + timedelta(seconds=FETCH_CACHE_TTL_SECONDS),
                        hit_count=0,
                    )
                )
            db.commit()
            return drafts, False
        raise HTTPException(
            status_code=503,
            detail="；".join(errors) or "所选平台暂时没有抓取到可用职位。",
        )

    async def _run_pipeline(self, session_id: str, payload: SearchSessionCreate) -> None:
        with Session(db_module.engine) as db:
            session = db.get(SearchSession, session_id)
            if not session:
                return

            try:
                profile = db.get(CandidateProfile, 1) or CandidateProfile(id=1)
                event_bus.publish(
                    session_id,
                    "fetching_jobs",
                    "正在抓取官网职位并进行代码级清洗。",
                )
                raw_jobs, fetch_cache_hit = await self._fetch_platform_jobs(
                    db,
                    payload,
                    profile,
                )
                if payload.force_refresh:
                    event_bus.publish(
                        session_id,
                        "fetch_force_refresh",
                        "已跳过职位抓取缓存，执行实时抓取。",
                    )
                elif fetch_cache_hit:
                    event_bus.publish(
                        session_id,
                        "fetch_cache_hit",
                        "命中职位抓取缓存，直接复用近 60 分钟结果。",
                    )
                official_stats: dict[str, int] = {}
                for platform in payload.platforms:
                    adapter = platform_gateway.get(platform)
                    stats = getattr(adapter, "last_run_stats", None)
                    if isinstance(stats, dict) and stats:
                        for key, value in stats.items():
                            official_stats[key] = int(official_stats.get(key, 0)) + int(value)
                if official_stats:
                    event_bus.publish(
                        session_id,
                        "code_cleaned",
                        (
                            "采集统计："
                            f"{official_stats.get('sources_selected', 0)} 个来源，"
                            f"{official_stats.get('sources_with_jobs', 0)} 个有职位，"
                            f"{official_stats.get('source_errors', 0)} 个报错，"
                            f"{official_stats.get('jobs_before_dedupe', 0)} 条原始职位，"
                            f"{official_stats.get('jobs_after_dedupe', 0)} 条进入排序。"
                        ),
                        official_stats,
                    )

                rule_matches = matching_service.filter_and_score(
                    profile=profile,
                    drafts=raw_jobs,
                    requested_targets=payload.job_targets,
                    requested_cities=payload.cities,
                    requested_keywords=payload.must_have_keywords,
                    salary_floor=payload.salary_floor,
                )
                db.exec(delete(JobMatch).where(JobMatch.session_id == session_id))
                db.exec(delete(JobListing).where(JobListing.session_id == session_id))
                db.commit()

                stored_jobs: list[JobListing] = []
                stored_matches: list[JobMatch] = []
                for rule_match in rule_matches:
                    draft = rule_match.draft
                    job = JobListing(
                        session_id=session_id,
                        platform=draft.raw_payload.get("platform", payload.platforms[0]),
                        source_company=draft.source_company,
                        source_site=draft.source_site,
                        job_id=draft.job_id,
                        title=draft.title,
                        department=draft.department,
                        employment_type=draft.employment_type,
                        location_raw=draft.location_raw,
                        location_city=draft.location_city,
                        location_country=draft.location_country,
                        remote_type=draft.remote_type,
                        description_html=draft.description_html,
                        description_text=draft.description_text,
                        requirements_text=draft.requirements_text,
                        skills_extracted=draft.skills_extracted,
                        posted_at=draft.posted_at,
                        apply_url=draft.apply_url,
                        salary_raw=draft.salary_raw,
                        salary_min=draft.salary_min,
                        salary_max=draft.salary_max,
                        lang=draft.lang,
                        crawl_time=draft.crawl_time or datetime.utcnow(),
                        raw_payload=draft.raw_payload,
                    )
                    db.add(job)
                    db.flush()
                    stored_jobs.append(job)

                    match = JobMatch(
                        session_id=session_id,
                        job_id=job.id,
                        rule_score=rule_match.rule_score,
                        final_score=rule_match.rule_score,
                        highlights=rule_match.highlights,
                        missing_keywords=rule_match.missing_keywords,
                        risk_flags=rule_match.risk_flags,
                    )
                    db.add(match)
                    db.flush()
                    stored_matches.append(match)
                db.commit()

                event_bus.publish(
                    session_id,
                    "rule_ranked",
                    f"清洗和规则排序后保留了 {len(stored_jobs)} 条职位。",
                    {"matches": len(stored_jobs)},
                )

                llm_target_jobs = stored_jobs[:LLM_ANALYSIS_LIMIT]
                analysis_batch = await llm_service.analyze_jobs(db, profile, llm_target_jobs)
                llm_by_job = {
                    result.job_id: result
                    for result in analysis_batch.results
                }
                provider = analysis_batch.metadata.provider
                degraded = analysis_batch.metadata.degraded
                notice = analysis_batch.metadata.notice

                for job, match in zip(stored_jobs, stored_matches, strict=True):
                    llm_result = llm_by_job.get(job.job_id)
                    if llm_result:
                        match.llm_score = llm_result.llm_score
                        match.final_score = round(
                            match.rule_score * 0.6 + llm_result.llm_score * 0.4,
                            2,
                        )
                        match.highlights = list(
                            dict.fromkeys(match.highlights + llm_result.highlights)
                        )
                        match.missing_keywords = list(
                            dict.fromkeys(
                                match.missing_keywords + llm_result.missing_keywords
                            )
                        )
                        match.risk_flags = list(
                            dict.fromkeys(match.risk_flags + llm_result.risk_flags)
                        )
                        match.llm_summary = llm_result.llm_summary
                        match.cached_llm = llm_result.cached
                    match.analysis_provider = provider
                    match.analysis_degraded = degraded
                    match.analysis_notice = notice
                    match.updated_at = datetime.utcnow()
                    db.add(match)
                db.commit()

                session.status = "ready"
                session.updated_at = datetime.utcnow()
                session.blocked_reason = None
                session.summary = "搜索完成，职位已清洗并排序。"
                session.analysis_provider = provider
                session.analysis_degraded = degraded
                session.analysis_notice = notice
                db.add(session)
                db.commit()
                self._set_session_meta(
                    db,
                    session_id,
                    retryable=False,
                    verification_url=None,
                    verification_title=None,
                    verification_opened_at=None,
                    blocked_at=None,
                )
                event_bus.publish(
                    session_id,
                    "llm_enriched",
                    f"排序已完成，分析提供方：{provider}。",
                    {
                        "matches": len(stored_jobs),
                        "llm_analyzed": len(llm_target_jobs),
                        "analysis_provider": provider,
                        "analysis_degraded": degraded,
                        "analysis_notice": notice,
                    },
                )
                event_bus.publish(session_id, "ready", "搜索任务已完成。")
            except PlatformBlockedError as error:
                detail = str(error)
                verification_url = error.verification_url
                primary_platform = payload.platforms[0] if payload.platforms else "official"
                risk_control_service.record_risk_event(
                    db,
                    primary_platform,
                    "blocked",
                    detail,
                )
                self._set_session_meta(
                    db,
                    session_id,
                    retryable=True,
                    verification_url=verification_url,
                    verification_title="搜索验证",
                    blocked_at=datetime.utcnow().isoformat(),
                    verification_opened_at=None,
                )
                session.status = "blocked"
                session.blocked_reason = detail
                session.summary = detail
                session.updated_at = datetime.utcnow()
                db.add(session)
                db.commit()
                event_bus.publish(
                    session_id,
                    "blocked",
                    detail,
                    {
                        "verification_url": verification_url,
                        "retryable": True,
                    },
                )
            except Exception as error:
                detail = str(error) or "搜索任务失败。"
                db.exec(delete(JobMatch).where(JobMatch.session_id == session_id))
                db.exec(delete(JobListing).where(JobListing.session_id == session_id))
                db.commit()
                session.status = "failed"
                session.blocked_reason = None
                session.summary = detail
                session.updated_at = datetime.utcnow()
                db.add(session)
                db.commit()
                self._set_session_meta(
                    db,
                    session_id,
                    retryable=False,
                    verification_url=None,
                    verification_title=None,
                    verification_opened_at=None,
                )
                event_bus.publish(session_id, "failed", detail)


search_service = SearchService()
