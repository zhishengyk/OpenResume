from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib

from sqlmodel import Session, delete, select

from .. import db as db_module
from ..models import CandidateProfile, JobListing, JobMatch, SearchSession
from ..schemas import SearchSessionCreate
from .events import event_bus
from .llm import llm_service
from .matching import matching_service
from .platform_gateway import platform_gateway


class SearchService:
    async def create_session(self, db: Session, payload: SearchSessionCreate) -> SearchSession:
        session = SearchSession(
            platform=payload.platform,
            mode=payload.mode,
            status="running",
            job_targets=payload.job_targets,
            cities=payload.cities,
            salary_floor=payload.salary_floor,
            must_have_keywords=payload.must_have_keywords,
            summary="Pipeline started. Rule filtering lands first, then cached or fresh LLM commentary follows.",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        event_bus.publish(session.id, "search_started", "Search session created.")
        asyncio.create_task(self._run_pipeline(session.id, payload))
        return session

    async def _run_pipeline(self, session_id: str, payload: SearchSessionCreate) -> None:
        with Session(db_module.engine) as db:
            session = db.get(SearchSession, session_id)
            if not session:
                return
            profile = db.get(CandidateProfile, 1) or CandidateProfile(id=1)
            adapter = platform_gateway.get(payload.platform)

            event_bus.publish(session_id, "fetching_jobs", "Fetching jobs from platform fixture and applying conservative pacing.")
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
                f"Rule filtering completed with {len(stored_jobs)} visible matches.",
                {"matches": len(stored_jobs)},
            )

            top_jobs = stored_jobs[:10]
            llm_results = await llm_service.analyze_jobs(db, profile, top_jobs)
            llm_by_key = {result.cache_key: result for result in llm_results}

            for job in top_jobs:
                cache_key = llm_service.provider.cache_key(job.platform, job.external_job_id, job.jd_hash)
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
                match.final_score = round(match.rule_score * 0.6 + llm_result.llm_score * 0.4, 2)
                match.highlights = list(dict.fromkeys(match.highlights + llm_result.highlights))
                match.missing_keywords = list(dict.fromkeys(match.missing_keywords + llm_result.missing_keywords))
                match.risk_flags = list(dict.fromkeys(match.risk_flags + llm_result.risk_flags))
                match.llm_summary = llm_result.llm_summary
                match.cached_llm = llm_result.cached
                match.updated_at = datetime.utcnow()
                db.add(match)
            db.commit()

            session.status = "ready"
            session.updated_at = datetime.utcnow()
            db.add(session)
            db.commit()
            event_bus.publish(
                session_id,
                "llm_enriched",
                f"LLM commentary refreshed for top {len(top_jobs)} matches.",
                {"matches": len(top_jobs)},
            )
            event_bus.publish(session_id, "ready", "Search session ready for review.")


search_service = SearchService()
