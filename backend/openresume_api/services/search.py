from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib

from fastapi import HTTPException
from sqlmodel import Session, delete, select

from .. import db as db_module
from ..adapters.base import PlatformBlockedError
from ..models import AppSetting, CandidateProfile, JobListing, JobMatch, SearchSession
from ..schemas import SearchSessionCreate
from .browser_session import browser_session_service
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
            platform=session.platform,
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
            platform=payload.platform,
            mode=payload.mode,
            status="running",
            job_targets=payload.job_targets,
            cities=payload.cities,
            salary_floor=payload.salary_floor,
            must_have_keywords=payload.must_have_keywords,
            summary=(
                "\u641c\u7d22\u4efb\u52a1\u5df2\u542f\u52a8\u3002"
                "\u7cfb\u7edf\u4f1a\u5148\u8fd4\u56de\u89c4\u5219\u7b5b\u9009\u7ed3\u679c\uff0c"
                "\u518d\u8865\u5145\u7f13\u5b58\u6216\u65b0\u751f\u6210\u7684\u6a21\u578b\u8bf4\u660e\u3002"
            ),
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
            verification_opened_at=None,
            blocked_at=None,
            last_retry_at=None,
        )
        event_bus.publish(
            session.id,
            "search_started",
            "\u641c\u7d22\u4efb\u52a1\u5df2\u521b\u5efa\u3002",
        )
        asyncio.create_task(self._run_pipeline(session.id, payload))
        return session

    async def retry_session(self, db: Session, session_id: str) -> SearchSession:
        session = db.get(SearchSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="\u641c\u7d22\u4efb\u52a1\u4e0d\u5b58\u5728\u3002")
        if session.status == "running":
            raise HTTPException(status_code=409, detail="\u5f53\u524d\u641c\u7d22\u4efb\u52a1\u4ecd\u5728\u8fd0\u884c\u4e2d\u3002")

        adapter = platform_gateway.get(session.platform)
        if hasattr(adapter, "ensure_search_ready"):
            try:
                await adapter.ensure_search_ready()
            except PlatformBlockedError as error:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"{str(error)} "
                        "\u8bf7\u5148\u6253\u5f00\u9a8c\u8bc1\u9875\u5e76\u5b8c\u6210\u767b\u5f55/\u9a8c\u8bc1\uff0c"
                        "\u7136\u540e\u518d\u70b9\u51fb\u201c\u9a8c\u8bc1\u540e\u91cd\u8bd5\u201d\u3002"
                    ),
                ) from error

        meta = self._get_session_meta(db, session_id)
        retry_count = int(meta.get("retry_count") or 0) + 1
        session.status = "running"
        session.blocked_reason = None
        session.summary = (
            "\u6b63\u5728\u91cd\u8bd5\u5f53\u524d\u641c\u7d22\u4efb\u52a1\u3002"
            "\u7cfb\u7edf\u4f1a\u4f18\u5148\u590d\u7528\u5df2\u6210\u529f\u7f13\u5b58\u7684 Boss \u641c\u7d22\u7ed3\u679c\u3002"
        )
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
            f"\u7b2c {retry_count} \u6b21\u91cd\u8bd5\u5df2\u542f\u52a8\u3002",
            {"retry_count": retry_count},
        )
        asyncio.create_task(self._run_pipeline(session.id, self._payload_from_session(session)))
        return session

    async def reopen_verification(self, db: Session, session_id: str) -> dict[str, str]:
        session = db.get(SearchSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="\u641c\u7d22\u4efb\u52a1\u4e0d\u5b58\u5728\u3002")

        meta = self._get_session_meta(db, session_id)
        verification_url = meta.get("verification_url")
        if not verification_url:
            raise HTTPException(
                status_code=409,
                detail="\u5f53\u524d\u641c\u7d22\u4efb\u52a1\u6ca1\u6709\u53ef\u7528\u7684\u9a8c\u8bc1\u9875\u94fe\u63a5\u3002",
            )

        await browser_session_service.open_url(
            db,
            session.platform,
            str(verification_url),
            "search_verification",
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
            "\u5df2\u91cd\u65b0\u6253\u5f00 Boss \u9a8c\u8bc1\u9875\uff0c\u8bf7\u5b8c\u6210\u9a8c\u8bc1\u540e\u518d\u70b9\u51fb\u91cd\u8bd5\u641c\u7d22\u3002",
        )
        return {
            "message": (
                "\u5df2\u91cd\u65b0\u6253\u5f00 Boss \u9a8c\u8bc1\u9875\uff0c"
                "\u8bf7\u5148\u5728\u6d4f\u89c8\u5668\u4e2d\u5b8c\u6210\u9a8c\u8bc1\u3002"
            )
        }

    async def _run_pipeline(self, session_id: str, payload: SearchSessionCreate) -> None:
        with Session(db_module.engine) as db:
            session = db.get(SearchSession, session_id)
            if not session:
                return

            try:
                profile = db.get(CandidateProfile, 1) or CandidateProfile(id=1)
                adapter = platform_gateway.get(payload.platform)
                if hasattr(adapter, "ensure_search_ready"):
                    await adapter.ensure_search_ready()

                event_bus.publish(
                    session_id,
                    "fetching_jobs",
                    (
                        "\u6b63\u5728\u6293\u53d6\u804c\u4f4d\uff0c"
                        "\u5e76\u6309\u4fdd\u5b88\u8282\u6d41\u7b56\u7565\u5904\u7406 Boss \u8bf7\u6c42\u3002"
                    ),
                )
                raw_jobs = await adapter.search_jobs(payload, profile)
                rule_matches = matching_service.filter_and_score(
                    profile=profile,
                    drafts=raw_jobs,
                    requested_targets=payload.job_targets,
                    requested_cities=payload.cities,
                    requested_keywords=payload.must_have_keywords,
                    salary_floor=payload.salary_floor,
                )
                rule_matches = rule_matches[:15]

                db.exec(delete(JobMatch).where(JobMatch.session_id == session_id))
                db.exec(delete(JobListing).where(JobListing.session_id == session_id))
                db.commit()

                stored_jobs: list[JobListing] = []
                for rule_match in rule_matches:
                    draft = rule_match.draft
                    jd_hash = hashlib.md5(draft.jd_text.encode("utf-8")).hexdigest()
                    job = JobListing(
                        session_id=session_id,
                        platform=payload.platform,
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
                        jd_text=draft.jd_text,
                        jd_hash=jd_hash,
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

                event_bus.publish(
                    session_id,
                    "rule_ranked",
                    (
                        f"\u89c4\u5219\u7b5b\u9009\u5b8c\u6210\uff0c"
                        f"\u5f53\u524d\u53ef\u89c1\u5c97\u4f4d {len(stored_jobs)} \u4e2a\u3002"
                    ),
                    {"matches": len(stored_jobs)},
                )

                top_jobs = stored_jobs[:10]
                llm_results = await llm_service.analyze_jobs(db, profile, top_jobs)
                llm_by_key = {result.cache_key: result for result in llm_results}

                for job in top_jobs:
                    cache_key = llm_service.provider.cache_key(
                        job.platform,
                        job.external_job_id,
                        job.jd_hash,
                    )
                    llm_result = llm_by_key.get(cache_key)
                    if not llm_result:
                        continue
                    match = db.exec(
                        select(JobMatch).where(
                            JobMatch.session_id == session_id,
                            JobMatch.job_id == job.id,
                        )
                    ).first()
                    if not match:
                        continue

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
                    match.updated_at = datetime.utcnow()
                    db.add(match)
                db.commit()

                session.status = "ready"
                session.updated_at = datetime.utcnow()
                session.blocked_reason = None
                session.summary = (
                    "\u641c\u7d22\u4efb\u52a1\u5df2\u5b8c\u6210\uff0c"
                    "\u7ed3\u679c\u4e2d\u5305\u542b\u771f\u5b9e Boss \u804c\u4f4d\u94fe\u63a5\u3002"
                )
                db.add(session)
                db.commit()
                self._set_session_meta(
                    db,
                    session_id,
                    retryable=False,
                    verification_url=None,
                    verification_opened_at=None,
                    blocked_at=None,
                )
                event_bus.publish(
                    session_id,
                    "llm_enriched",
                    (
                        f"\u6a21\u578b\u8bf4\u660e\u5df2\u8865\u5145\u5230"
                        f"\u524d {len(top_jobs)} \u4e2a\u5c97\u4f4d\u3002"
                    ),
                    {"matches": len(top_jobs)},
                )
                event_bus.publish(
                    session_id,
                    "ready",
                    "\u641c\u7d22\u4efb\u52a1\u5df2\u5b8c\u6210\uff0c\u53ef\u5f00\u59cb\u67e5\u770b\u7ed3\u679c\u3002",
                )
            except PlatformBlockedError as error:
                detail = str(error)
                verification_url = error.verification_url

                risk_control_service.record_risk_event(
                    db,
                    payload.platform,
                    "blocked",
                    detail,
                )
                self._set_session_meta(
                    db,
                    session_id,
                    retryable=True,
                    verification_url=verification_url,
                    blocked_at=datetime.utcnow().isoformat(),
                    verification_opened_at=None,
                )

                if verification_url:
                    session.summary = (
                        f"{detail}"
                        "\u8bf7\u5148\u70b9\u51fb\u201c\u91cd\u65b0\u6253\u5f00\u9a8c\u8bc1\u9875\u201d\u5b8c\u6210\u767b\u5f55/\u9a8c\u8bc1\uff0c\u518d"
                        "\u70b9\u51fb\u201c\u9a8c\u8bc1\u540e\u91cd\u8bd5\u201d\u3002"
                    )
                else:
                    session.summary = detail

                session.status = "blocked"
                session.blocked_reason = detail
                session.updated_at = datetime.utcnow()
                db.add(session)
                db.commit()
                event_bus.publish(
                    session_id,
                    "blocked",
                    session.summary,
                    {
                        "verification_url": verification_url,
                        "verification_opened": False,
                        "retryable": True,
                    },
                )
            except Exception as error:
                detail = str(error) or "\u641c\u7d22\u4efb\u52a1\u5931\u8d25\u3002"
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
                    verification_opened_at=None,
                )
                event_bus.publish(session_id, "failed", detail)


search_service = SearchService()
