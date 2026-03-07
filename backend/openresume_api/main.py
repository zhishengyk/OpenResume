from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import json
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from .adapters.base import PlatformBlockedError
from .config import settings
from .db import get_session, init_db
from .models import (
    ApplicationAttempt,
    CandidateProfile,
    JobListing,
    JobMatch,
    SearchSession,
)
from .schemas import (
    AppStateResponse,
    CandidateProfileUpdate,
    EmergencyStopRequest,
    JobMatchResponse,
    PlatformSessionResponse,
    RiskConsentCreate,
    RiskStatusResponse,
    SearchSessionCreate,
)
from .services.browser_session import browser_session_service
from .services.compliance import compliance_service
from .services.events import event_bus
from .services.platform_gateway import platform_gateway
from .services.profile import profile_service
from .services.risk import risk_control_service
from .services.search import search_service

SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    try:
        yield
    finally:
        await browser_session_service.shutdown()


app = FastAPI(title="OpenResume 本地接口", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


def profile_response(profile: CandidateProfile) -> dict:
    return {
        "id": profile.id,
        "full_name": profile.full_name,
        "headline": profile.headline,
        "summary": profile.summary,
        "target_roles": profile.target_roles,
        "preferred_cities": profile.preferred_cities,
        "salary_floor": profile.salary_floor,
        "years_experience": profile.years_experience,
        "degree": profile.degree,
        "skills": profile.skills,
        "must_have_keywords": profile.must_have_keywords,
        "source_filename": profile.source_filename,
        "source_language": profile.source_language,
        "updated_at": profile.updated_at,
    }


def match_response(match: JobMatch, job: JobListing) -> JobMatchResponse:
    return JobMatchResponse(
        id=match.id,
        job_id=job.id,
        platform=job.platform,
        external_job_id=job.external_job_id,
        title=job.title,
        company_name=job.company_name,
        city=job.city,
        salary_text=job.salary_text,
        experience_text=job.experience_text,
        degree_text=job.degree_text,
        work_mode=job.work_mode,
        url=job.url,
        jd_excerpt=job.jd_text[:160],
        rule_score=match.rule_score,
        llm_score=match.llm_score,
        final_score=match.final_score,
        highlights=match.highlights,
        missing_keywords=match.missing_keywords,
        risk_flags=match.risk_flags,
        llm_summary=match.llm_summary,
        cached_llm=match.cached_llm,
    )


@app.get("/api/app-state", response_model=AppStateResponse)
def get_app_state(db: SessionDep) -> AppStateResponse:
    return AppStateResponse(**compliance_service.app_state(db))


@app.post("/api/risk-consents")
def create_risk_consent(payload: RiskConsentCreate, db: SessionDep):
    return compliance_service.record_consent(
        db,
        consent_type=payload.consent_type,
        platform=payload.platform,
        version=payload.version,
    )


@app.post("/api/resume/upload")
async def upload_resume(db: SessionDep, file: UploadFile = File(...)):
    content = await file.read()
    try:
        parsed = profile_service.parse_resume(file.filename or "resume.pdf", content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    profile = profile_service.save_profile(db, parsed)
    return profile_response(profile)


@app.get("/api/profile")
def get_profile(db: SessionDep):
    return profile_response(profile_service.load_or_create(db))


@app.put("/api/profile")
def update_profile(payload: CandidateProfileUpdate, db: SessionDep):
    profile = profile_service.save_profile(db, payload)
    return profile_response(profile)


@app.get("/api/platforms")
def list_platforms():
    return platform_gateway.list_capabilities()


@app.get("/api/platforms/{platform}/capabilities")
def get_platform_capabilities(platform: str):
    return platform_gateway.get(platform).capability()


@app.post("/api/platforms/{platform}/session/start", response_model=PlatformSessionResponse)
async def start_platform_session(platform: str, db: SessionDep):
    adapter = platform_gateway.get(platform)
    await adapter.start_session(db)
    state = await adapter.session_state(db)
    return PlatformSessionResponse(
        platform=platform,
        active=state["active"],
        search_ready=bool(state.get("search_ready")),
        last_started_at=(
            datetime.fromisoformat(state["last_started_at"])
            if state["last_started_at"]
            else None
        ),
        storage_dir=state["storage_dir"],
        recommended_account_notice="建议使用独立账号或独立会话目录进行引导投递。",
    )


@app.get("/api/platforms/{platform}/session", response_model=PlatformSessionResponse)
async def get_platform_session(platform: str, db: SessionDep):
    state = browser_session_service.state(db, platform)
    return PlatformSessionResponse(
        platform=platform,
        active=state["active"],
        search_ready=bool(state.get("search_ready")),
        last_started_at=(
            datetime.fromisoformat(state["last_started_at"])
            if state["last_started_at"]
            else None
        ),
        storage_dir=state["storage_dir"],
        recommended_account_notice="建议使用独立账号或独立会话目录进行引导投递。",
    )


@app.get("/api/platforms/{platform}/risk-status", response_model=RiskStatusResponse)
def get_risk_status(platform: str, db: SessionDep):
    return RiskStatusResponse(**risk_control_service.current_status(db, platform))


@app.post("/api/search-sessions")
async def create_search_session(payload: SearchSessionCreate, db: SessionDep):
    adapter = platform_gateway.get(payload.platform)
    capability = adapter.capability()
    if not capability.search_supported:
        raise HTTPException(status_code=409, detail="\u5f53\u524d\u5e73\u53f0\u6682\u4e0d\u652f\u6301\u641c\u7d22\u80fd\u529b\u3002")
    if (
        payload.mode == "guided_apply"
        and not compliance_service.has_guided_apply_consent(db, payload.platform)
    ):
        raise HTTPException(status_code=403, detail="\u8bf7\u5148\u5b8c\u6210\u5f15\u5bfc\u6295\u9012\u98ce\u9669\u786e\u8ba4\u3002")

    if payload.platform == "boss" and settings.boss_search_mode.lower().strip() == "live":
        state = await adapter.session_state(db)
        if not state.get("active"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "\u8bf7\u5148\u542f\u52a8 Boss \u4f1a\u8bdd\uff0c"
                    "\u5e76\u5728\u4f1a\u8bdd\u6d4f\u89c8\u5668\u4e2d\u5b8c\u6210\u767b\u5f55/\u9a8c\u8bc1\u3002"
                ),
            )
        try:
            await adapter.ensure_search_ready()
            browser_session_service.set_search_ready(
                db,
                payload.platform,
                True,
                reason="search_gate_passed",
            )
        except PlatformBlockedError as error:
            browser_session_service.set_search_ready(
                db,
                payload.platform,
                False,
                reason="search_gate_blocked",
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{str(error)} "
                    "\u8bf7\u5148\u70b9\u51fb\u201c\u91cd\u65b0\u6253\u5f00\u9a8c\u8bc1\u9875\u201d\uff0c"
                    "\u5b8c\u6210\u767b\u5f55/\u9a8c\u8bc1\u540e\u518d\u91cd\u8bd5\u3002"
                ),
            ) from error
    return await search_service.create_session(db, payload)


@app.get("/api/search-sessions")
def list_search_sessions(db: SessionDep):
    sessions = db.exec(
        select(SearchSession).order_by(SearchSession.created_at.desc())
    ).all()
    return sessions


@app.get("/api/search-sessions/{session_id}")
def get_search_session(session_id: str, db: SessionDep):
    session = db.get(SearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="\u641c\u7d22\u4efb\u52a1\u4e0d\u5b58\u5728\u3002")
    return session


@app.post("/api/search-sessions/{session_id}/retry")
async def retry_search_session(session_id: str, db: SessionDep):
    return await search_service.retry_session(db, session_id)


@app.post("/api/search-sessions/{session_id}/open-verification")
async def open_search_verification(session_id: str, db: SessionDep):
    return await search_service.reopen_verification(db, session_id)


@app.get("/api/search-sessions/{session_id}/matches", response_model=list[JobMatchResponse])
def get_search_matches(session_id: str, db: SessionDep):
    matches = db.exec(
        select(JobMatch)
        .where(JobMatch.session_id == session_id)
        .order_by(JobMatch.final_score.desc())
    ).all()
    jobs = {
        job.id: job
        for job in db.exec(
            select(JobListing).where(JobListing.session_id == session_id)
        ).all()
    }
    return [
        match_response(match, jobs[match.job_id])
        for match in matches
        if match.job_id in jobs
    ]


@app.get("/api/search-sessions/{session_id}/events")
async def stream_search_events(session_id: str):
    async def event_generator():
        async for event in event_bus.stream(session_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/jobs/{job_id}/open-review")
async def open_review(job_id: str, db: SessionDep):
    job = db.get(JobListing, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="职位不存在。")
    adapter = platform_gateway.get(job.platform)
    message = await adapter.open_review(job.url)
    return {"message": message}


@app.post("/api/jobs/{job_id}/guided-apply")
async def guided_apply(job_id: str, db: SessionDep):
    job = db.get(JobListing, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="职位不存在。")
    if not compliance_service.has_guided_apply_consent(db, job.platform):
        raise HTTPException(status_code=403, detail="请先完成引导投递风险确认。")

    risk_control_service.ensure_guided_apply_allowed(db, job.platform)
    profile = profile_service.load_or_create(db)
    adapter = platform_gateway.get(job.platform)

    attempt = ApplicationAttempt(
        job_id=job.id,
        platform=job.platform,
        mode="guided_apply",
        status="running",
        message="正在准备专用投递流程，并会在最终提交前停止。",
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    try:
        message = await adapter.guided_apply(job.url, profile)
        attempt.status = "prepared"
        attempt.message = message
        attempt.updated_at = datetime.utcnow()
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        return attempt
    except Exception as error:
        attempt.status = "failed"
        attempt.message = str(error)
        attempt.updated_at = datetime.utcnow()
        db.add(attempt)
        db.commit()
        raise


@app.get("/api/application-attempts")
def list_application_attempts(db: SessionDep):
    return db.exec(
        select(ApplicationAttempt).order_by(ApplicationAttempt.created_at.desc())
    ).all()


@app.post("/api/application-attempts/{attempt_id}/cancel")
def cancel_application_attempt(attempt_id: str, db: SessionDep):
    attempt = db.get(ApplicationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="投递记录不存在。")
    attempt.status = "cancelled"
    attempt.updated_at = datetime.utcnow()
    attempt.message = "已由用户取消。"
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@app.post("/api/emergency-stop")
def set_emergency_stop(payload: EmergencyStopRequest, db: SessionDep):
    return risk_control_service.set_emergency_stop(db, payload.active)
