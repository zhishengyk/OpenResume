from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import hashlib
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import insert as sql_insert
from sqlmodel import Session, delete, select

from .. import db as db_module
from ..adapters.base import NormalizedJobDraft, PlatformBlockedError
from ..config import settings
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
    @staticmethod
    def _match_limit() -> int:
        return max(1, settings.search_match_limit)

    @staticmethod
    def _company_job_limit() -> int:
        return max(1, settings.search_company_job_limit)

    @staticmethod
    def _effective_match_limit(payload: SearchSessionCreate) -> int:
        requested = int(payload.match_limit or settings.search_match_limit)
        return max(1, min(1000, requested))

    @staticmethod
    def _effective_company_job_limit(payload: SearchSessionCreate) -> int:
        requested = int(payload.company_job_limit or settings.search_company_job_limit)
        return max(1, min(1000, requested))

    def _limit_rule_matches(
        self,
        rule_matches,
        *,
        match_limit: int,
        company_job_limit: int,
    ):
        limited = []
        company_counts: dict[str, int] = {}
        for item in rule_matches:
            company = item.draft.source_company.strip() or "unknown"
            if company_counts.get(company, 0) >= company_job_limit:
                continue
            limited.append(item)
            company_counts[company] = company_counts.get(company, 0) + 1
            if len(limited) >= match_limit:
                break
        return limited

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

    def _deserialize_drafts(
        self,
        payload_json: list[dict[str, Any]],
    ) -> list[NormalizedJobDraft]:
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
        return {
            "platforms": sorted(dict.fromkeys(payload.platforms)),
            "source_variants": sorted(dict.fromkeys(payload.source_variants or [])),
            "source_companies": sorted(dict.fromkeys(payload.source_companies or [])),
            "keyword_basis": sorted(dict.fromkeys(keywords)),
            "company_job_limit": SearchService._effective_company_job_limit(payload),
        }

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
            match_limit=session.match_limit,
            company_job_limit=session.company_job_limit,
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
            match_limit=self._effective_match_limit(payload),
            company_job_limit=self._effective_company_job_limit(payload),
            force_refresh=payload.force_refresh,
            analysis_status="pending",
            analysis_provider="heuristic",
            analysis_degraded=False,
            analysis_notice=None,
            summary="Search started. Fetching and cleaning jobs.",
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
            fetch_ms=None,
            rule_rank_ms=None,
            persist_ms=None,
            time_to_ready_ms=None,
            llm_ms=None,
            time_to_llm_enriched_ms=None,
        )
        event_bus.publish(session.id, "search_started", "Search task created.")
        asyncio.create_task(self._run_pipeline(session.id, payload))
        return session

    async def retry_session(self, db: Session, session_id: str) -> SearchSession:
        session = db.get(SearchSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Search session not found.")
        if session.status == "running":
            raise HTTPException(status_code=409, detail="Search session is still running.")

        meta = self._get_session_meta(db, session_id)
        retry_count = int(meta.get("retry_count") or 0) + 1
        session.status = "running"
        session.analysis_status = "pending"
        session.analysis_provider = "heuristic"
        session.analysis_degraded = False
        session.analysis_notice = None
        session.blocked_reason = None
        session.summary = "Retrying search."
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
            fetch_ms=None,
            rule_rank_ms=None,
            persist_ms=None,
            time_to_ready_ms=None,
            llm_ms=None,
            time_to_llm_enriched_ms=None,
        )
        event_bus.reset(session_id)
        event_bus.publish(
            session_id,
            "search_restarted",
            f"Retry #{retry_count} started.",
            {"retry_count": retry_count},
        )
        asyncio.create_task(self._run_pipeline(session.id, self._payload_from_session(session)))
        return session

    async def reopen_verification(self, db: Session, session_id: str) -> dict[str, str]:
        session = db.get(SearchSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Search session not found.")

        meta = self._get_session_meta(db, session_id)
        verification_url = meta.get("verification_url")
        if not verification_url:
            raise HTTPException(
                status_code=409,
                detail="This session does not have a verification window to reopen.",
            )

        self._set_session_meta(
            db,
            session_id,
            verification_opened_at=datetime.utcnow().isoformat(),
            retryable=True,
        )
        event_bus.publish(
            session_id,
            "verification_opened",
            "Verification window is ready to reopen.",
        )
        return {
            "url": str(verification_url),
            "title": str(meta.get("verification_title") or "Search verification"),
            "message": "Complete verification in the popup and retry the search.",
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
            detail="; ".join(errors) or "Selected platforms returned no usable jobs.",
        )

    async def _run_pipeline(self, session_id: str, payload: SearchSessionCreate) -> None:
        with Session(db_module.engine) as db:
            session = db.get(SearchSession, session_id)
            if not session:
                return

            pipeline_started_at = perf_counter()
            try:
                profile = db.get(CandidateProfile, 1) or CandidateProfile(id=1)

                event_bus.publish(
                    session_id,
                    "fetching_jobs",
                    "Fetching jobs from official career sites.",
                )
                fetch_started_at = perf_counter()
                raw_jobs, fetch_cache_hit = await self._fetch_platform_jobs(db, payload, profile)
                fetch_ms = int((perf_counter() - fetch_started_at) * 1000)

                if payload.force_refresh:
                    event_bus.publish(
                        session_id,
                        "fetch_force_refresh",
                        "Fetch cache bypassed. Running a live fetch.",
                    )
                elif fetch_cache_hit:
                    event_bus.publish(
                        session_id,
                        "fetch_cache_hit",
                        "Fetch cache hit. Reusing recent results.",
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
                            f"Sources: {official_stats.get('sources_selected', 0)}, "
                            f"with jobs: {official_stats.get('sources_with_jobs', 0)}, "
                            f"errors: {official_stats.get('source_errors', 0)}, "
                            f"raw jobs: {official_stats.get('jobs_before_dedupe', 0)}, "
                            f"ranked jobs: {official_stats.get('jobs_after_dedupe', 0)}."
                        ),
                        official_stats,
                    )

                rule_started_at = perf_counter()
                rule_matches = matching_service.filter_and_score(
                    profile=profile,
                    drafts=raw_jobs,
                    requested_targets=payload.job_targets,
                    requested_cities=payload.cities,
                    requested_keywords=payload.must_have_keywords,
                    salary_floor=payload.salary_floor,
                )
                rule_matches = self._limit_rule_matches(
                    rule_matches,
                    match_limit=self._effective_match_limit(payload),
                    company_job_limit=self._effective_company_job_limit(payload),
                )
                rule_rank_ms = int((perf_counter() - rule_started_at) * 1000)

                db.exec(delete(JobMatch).where(JobMatch.session_id == session_id))
                db.exec(delete(JobListing).where(JobListing.session_id == session_id))
                db.commit()

                persist_started_at = perf_counter()
                job_rows: list[dict[str, Any]] = []
                match_rows: list[dict[str, Any]] = []
                default_platform = payload.platforms[0] if payload.platforms else "official"
                now = datetime.utcnow()

                for rule_match in rule_matches:
                    draft = rule_match.draft
                    listing_id = str(uuid4())
                    job_rows.append(
                        {
                            "id": listing_id,
                            "session_id": session_id,
                            "platform": str(draft.raw_payload.get("platform") or default_platform),
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
                            "skills_extracted": draft.skills_extracted,
                            "posted_at": draft.posted_at,
                            "apply_url": draft.apply_url,
                            "salary_raw": draft.salary_raw,
                            "salary_min": draft.salary_min,
                            "salary_max": draft.salary_max,
                            "lang": draft.lang,
                            "crawl_time": draft.crawl_time or now,
                            "raw_payload": draft.raw_payload,
                            "created_at": now,
                        }
                    )
                    match_rows.append(
                        {
                            "id": str(uuid4()),
                            "session_id": session_id,
                            "job_id": listing_id,
                            "rule_score": rule_match.rule_score,
                            "final_score": rule_match.rule_score,
                            "highlights": rule_match.highlights,
                            "missing_keywords": rule_match.missing_keywords,
                            "risk_flags": rule_match.risk_flags,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )

                if job_rows:
                    db.execute(sql_insert(JobListing), job_rows)
                if match_rows:
                    db.execute(sql_insert(JobMatch), match_rows)
                db.commit()
                persist_ms = int((perf_counter() - persist_started_at) * 1000)

                event_bus.publish(
                    session_id,
                    "rule_ranked",
                    f"Rule ranking kept {len(job_rows)} jobs.",
                    {"matches": len(job_rows)},
                )

                time_to_ready_ms = int((perf_counter() - pipeline_started_at) * 1000)
                session.status = "ready"
                session.analysis_status = "pending"
                session.analysis_provider = "heuristic"
                session.analysis_degraded = False
                session.analysis_notice = None
                session.blocked_reason = None
                session.summary = "Search results are ready. LLM analysis is running in background."
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
                    blocked_at=None,
                    fetch_ms=fetch_ms,
                    rule_rank_ms=rule_rank_ms,
                    persist_ms=persist_ms,
                    time_to_ready_ms=time_to_ready_ms,
                )
                event_bus.publish(
                    session_id,
                    "ready",
                    "Results are ready. LLM analysis will update them in background.",
                )
                asyncio.create_task(self._run_llm_enrichment(session_id))
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
                    verification_title="Search verification",
                    blocked_at=datetime.utcnow().isoformat(),
                    verification_opened_at=None,
                )
                session.status = "blocked"
                session.analysis_status = "failed"
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
                detail = str(error) or "Search task failed."
                db.exec(delete(JobMatch).where(JobMatch.session_id == session_id))
                db.exec(delete(JobListing).where(JobListing.session_id == session_id))
                db.commit()
                session.status = "failed"
                session.analysis_status = "failed"
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

    async def _run_llm_enrichment(self, session_id: str) -> None:
        llm_started_at = perf_counter()
        with Session(db_module.engine) as db:
            session = db.get(SearchSession, session_id)
            if not session or session.status != "ready":
                return

            session.analysis_status = "running"
            session.updated_at = datetime.utcnow()
            db.add(session)
            db.commit()
            event_bus.publish(
                session_id,
                "llm_started",
                "LLM analysis started in background.",
            )

            try:
                profile = db.get(CandidateProfile, 1) or CandidateProfile(id=1)
                match_rows = db.exec(
                    select(JobMatch)
                    .where(JobMatch.session_id == session_id)
                    .order_by(JobMatch.final_score.desc())
                ).all()
                jobs_by_id = {
                    job.id: job
                    for job in db.exec(
                        select(JobListing).where(JobListing.session_id == session_id)
                    ).all()
                }
                job_match_pairs = [
                    (jobs_by_id[match.job_id], match)
                    for match in match_rows
                    if match.job_id in jobs_by_id
                ]
                if not job_match_pairs:
                    session.analysis_status = "ready"
                    session.updated_at = datetime.utcnow()
                    db.add(session)
                    db.commit()
                    self._set_session_meta(
                        db,
                        session_id,
                        llm_ms=0,
                        time_to_llm_enriched_ms=int(
                            self._get_session_meta(db, session_id).get("time_to_ready_ms") or 0
                        ),
                    )
                    return

                target_pairs = job_match_pairs[:LLM_ANALYSIS_LIMIT]
                analysis_batch = await llm_service.analyze_jobs(
                    db,
                    profile,
                    [job for job, _match in target_pairs],
                )
                llm_by_job = {result.job_id: result for result in analysis_batch.results}
                provider = analysis_batch.metadata.provider
                degraded = analysis_batch.metadata.degraded
                notice = analysis_batch.metadata.notice

                db.refresh(session)
                if session.status != "ready" or session.analysis_status != "running":
                    return

                for job, match in job_match_pairs:
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

                llm_ms = int((perf_counter() - llm_started_at) * 1000)
                ready_ms = int(self._get_session_meta(db, session_id).get("time_to_ready_ms") or 0)
                session.analysis_status = "ready"
                session.analysis_provider = provider
                session.analysis_degraded = degraded
                session.analysis_notice = notice
                session.summary = "Search finished. LLM analysis has been applied."
                session.updated_at = datetime.utcnow()
                db.add(session)
                db.commit()
                self._set_session_meta(
                    db,
                    session_id,
                    llm_ms=llm_ms,
                    time_to_llm_enriched_ms=ready_ms + llm_ms,
                )
                event_bus.publish(
                    session_id,
                    "llm_enriched",
                    f"LLM analysis applied with provider: {provider}.",
                    {
                        "matches": len(job_match_pairs),
                        "llm_analyzed": len(target_pairs),
                        "analysis_provider": provider,
                        "analysis_degraded": degraded,
                        "analysis_notice": notice,
                    },
                )
            except Exception as error:
                detail = str(error) or "LLM analysis failed."
                db.refresh(session)
                if session.status == "ready":
                    session.analysis_status = "failed"
                    session.analysis_degraded = True
                    session.analysis_notice = detail
                    session.summary = "Search finished, but background LLM analysis failed."
                    session.updated_at = datetime.utcnow()
                    db.add(session)
                    db.commit()
                self._set_session_meta(
                    db,
                    session_id,
                    llm_ms=int((perf_counter() - llm_started_at) * 1000),
                )
                event_bus.publish(session_id, "llm_failed", detail)


search_service = SearchService()
