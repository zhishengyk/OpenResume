from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib

from sqlmodel import Session, delete, select

from .. import db as db_module
from ..adapters.base import PlatformBlockedError
from ..models import CandidateProfile, JobListing, JobMatch, SearchSession
from ..schemas import SearchSessionCreate
from .events import event_bus
from .llm import llm_service
from .matching import matching_service
from .platform_gateway import platform_gateway
from .risk import risk_control_service


class SearchService:
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
            summary="搜索任务已启动。系统会先返回规则筛选结果，再补充缓存或新生成的模型说明。",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        event_bus.publish(session.id, "search_started", "搜索任务已创建。")
        asyncio.create_task(self._run_pipeline(session.id, payload))
        return session

    async def _run_pipeline(self, session_id: str, payload: SearchSessionCreate) -> None:
        with Session(db_module.engine) as db:
            session = db.get(SearchSession, session_id)
            if not session:
                return
            try:
                profile = db.get(CandidateProfile, 1) or CandidateProfile(id=1)
                adapter = platform_gateway.get(payload.platform)

                event_bus.publish(
                    session_id,
                    "fetching_jobs",
                    "正在抓取职位并按保守节流策略处理平台请求。",
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
                    f"规则筛选完成，当前可见岗位 {len(stored_jobs)} 个。",
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
                session.summary = "搜索任务已完成，结果中包含真实职位链接。"
                db.add(session)
                db.commit()
                event_bus.publish(
                    session_id,
                    "llm_enriched",
                    f"模型说明已补充到前 {len(top_jobs)} 个岗位。",
                    {"matches": len(top_jobs)},
                )
                event_bus.publish(session_id, "ready", "搜索任务已完成，可开始查看结果。")
            except PlatformBlockedError as error:
                detail = str(error)
                risk_control_service.record_risk_event(
                    db,
                    payload.platform,
                    "blocked",
                    detail,
                )
                session.status = "blocked"
                session.blocked_reason = detail
                session.summary = detail
                session.updated_at = datetime.utcnow()
                db.add(session)
                db.commit()
                event_bus.publish(session_id, "blocked", detail)
            except Exception as error:
                detail = str(error) or "搜索任务失败。"
                session.status = "failed"
                session.blocked_reason = None
                session.summary = detail
                session.updated_at = datetime.utcnow()
                db.add(session)
                db.commit()
                event_bus.publish(session_id, "failed", detail)


search_service = SearchService()
