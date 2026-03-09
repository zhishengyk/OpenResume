from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, delete

from .. import db as db_module
from ..adapters.base import NormalizedJobDraft, PlatformBlockedError
from ..models import AppSetting, CandidateProfile, JobListing, JobMatch, SearchSession
from ..schemas import SearchSessionCreate
from .events import event_bus
from .llm import llm_service
from .matching import matching_service
from .platform_gateway import platform_gateway
from .risk import risk_control_service


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
    def _payload_from_session(session: SearchSession) -> SearchSessionCreate:
        return SearchSessionCreate(
            platforms=list(session.requested_platforms or []),
            mode=session.mode,
            job_targets=list(session.job_targets or []),
            cities=list(session.cities or []),
            salary_floor=session.salary_floor,
            must_have_keywords=list(session.must_have_keywords or []),
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
            summary="Search started. Official pages are being cleaned before model ranking.",
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
        event_bus.publish(session.id, "search_started", "Search session created.")
        asyncio.create_task(self._run_pipeline(session.id, payload))
        return session

    async def retry_session(self, db: Session, session_id: str) -> SearchSession:
        session = db.get(SearchSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Search session not found.")
        if session.status == "running":
            raise HTTPException(status_code=409, detail="Search session is already running.")

        meta = self._get_session_meta(db, session_id)
        retry_count = int(meta.get("retry_count") or 0) + 1
        session.status = "running"
        session.blocked_reason = None
        session.summary = "Retrying this search session."
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
            raise HTTPException(status_code=409, detail="This search session does not have a verification URL.")

        self._set_session_meta(
            db,
            session_id,
            verification_opened_at=datetime.utcnow().isoformat(),
            retryable=True,
        )
        event_bus.publish(
            session_id,
            "verification_opened",
            "Verification window can be reopened in-app.",
        )
        return {
            "url": str(verification_url),
            "title": str(meta.get("verification_title") or "Search verification"),
            "message": "Open the verification window, complete the challenge, then retry.",
        }

    async def _fetch_platform_jobs(
        self,
        payload: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
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
            return drafts
        raise HTTPException(
            status_code=503,
            detail="; ".join(errors) or "No jobs could be collected from the selected platforms.",
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
                    "Fetching official sites and applying code-based cleaning.",
                )
                raw_jobs = await self._fetch_platform_jobs(payload, profile)
                rule_matches = matching_service.filter_and_score(
                    profile=profile,
                    drafts=raw_jobs,
                    requested_targets=payload.job_targets,
                    requested_cities=payload.cities,
                    requested_keywords=payload.must_have_keywords,
                    salary_floor=payload.salary_floor,
                )
                rule_matches = rule_matches[:20]

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
                        external_job_id=draft.external_job_id,
                        title=draft.title,
                        company_name=draft.company_name,
                        city=draft.city,
                        salary_text=draft.salary_text,
                        salary_min=draft.salary_min,
                        salary_max=draft.salary_max,
                        experience_text=draft.experience_text,
                        degree_text=draft.degree_text,
                        work_mode=draft.work_mode,
                        url=draft.url,
                        detail_url=draft.detail_url or draft.url,
                        apply_url=draft.apply_url,
                        source_company_url=draft.source_company_url,
                        apply_requires_login=draft.apply_requires_login,
                        jd_text=draft.jd_text,
                        jd_hash=draft.jd_hash,
                        raw_payload=draft.raw_payload,
                    )
                    db.add(job)
                    db.commit()
                    db.refresh(job)
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
                    db.commit()
                    db.refresh(match)
                    stored_matches.append(match)

                event_bus.publish(
                    session_id,
                    "rule_ranked",
                    f"Code cleaning and rule ranking kept {len(stored_jobs)} jobs.",
                    {"matches": len(stored_jobs)},
                )

                analysis_batch = await llm_service.analyze_jobs(db, profile, stored_jobs)
                llm_by_job = {
                    result.external_job_id: result
                    for result in analysis_batch.results
                }
                provider = analysis_batch.metadata.provider
                degraded = analysis_batch.metadata.degraded
                notice = analysis_batch.metadata.notice

                for job, match in zip(stored_jobs, stored_matches, strict=True):
                    llm_result = llm_by_job.get(job.external_job_id)
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
                session.summary = "Search complete. Jobs were cleaned in code before ranking."
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
                    f"Ranking finished with provider {provider}.",
                    {
                        "matches": len(stored_jobs),
                        "analysis_provider": provider,
                        "analysis_degraded": degraded,
                        "analysis_notice": notice,
                    },
                )
                event_bus.publish(session_id, "ready", "Search session is ready.")
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
                detail = str(error) or "Search session failed."
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
