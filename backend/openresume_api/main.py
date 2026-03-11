from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import json
import re
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

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
    ApplicationAttemptResponse,
    CandidateProfileUpdate,
    EmergencyStopRequest,
    JobLocationOptionResponse,
    JobMatchResponse,
    LLMConnectionTestResponse,
    LLMModelListResponse,
    LLMRuntimeProbeRequest,
    PlatformSessionResponse,
    RiskConsentCreate,
    RiskStatusResponse,
    RuntimeConfigResponse,
    RuntimeConfigUpdateRequest,
    SearchSessionCreate,
    SearchSessionResponse,
    VerificationWindowResponse,
)
from .services.compliance import compliance_service
from .services.events import event_bus
from .services.platform_gateway import platform_gateway
from .services.profile import profile_service
from .services.risk import risk_control_service
from .services.runtime_config import runtime_config_service
from .services.search import search_service
from .career_collectors import get_available_companies, get_available_variants, load_sources

SessionDep = Annotated[Session, Depends(get_session)]

RECOMMENDED_ACCOUNT_NOTICE = (
    "如遇官网登录或验证码，请优先使用应用内验证窗口完成。"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="OpenResume Local API", version="0.2.0", lifespan=lifespan)
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
        "tech_stack": profile.tech_stack,
        "project_experiences": profile.project_experiences,
        "awards": profile.awards,
        "source_filename": profile.source_filename,
        "source_language": profile.source_language,
        "raw_text": profile.raw_text,
        "profile_signature": profile_service.profile_signature(profile),
        "updated_at": profile.updated_at,
    }


def platform_session_response(platform: str, state: dict) -> PlatformSessionResponse:
    last_started_at = state.get("last_started_at")
    if isinstance(last_started_at, str) and last_started_at:
        last_started_value = datetime.fromisoformat(last_started_at)
    elif isinstance(last_started_at, datetime):
        last_started_value = last_started_at
    else:
        last_started_value = None

    return PlatformSessionResponse(
        platform=platform,
        active=bool(state.get("active")),
        search_ready=bool(state.get("search_ready")),
        last_started_at=last_started_value,
        storage_dir=str(state.get("storage_dir") or ""),
        recommended_account_notice=str(
            state.get("recommended_account_notice") or RECOMMENDED_ACCOUNT_NOTICE
        ),
    )


def match_response(match: JobMatch, job: JobListing) -> JobMatchResponse:
    location_options = [
        JobLocationOptionResponse(
            listing_id=job.id,
            location_city=job.location_city,
            location_raw=job.location_raw,
            apply_url=job.apply_url,
        )
    ]
    location_labels = list(
        dict.fromkeys(
            (
                option.location_city.strip()
                or option.location_raw.strip()
                or "地点未知"
            )
            for option in location_options
        )
    )
    return JobMatchResponse(
        id=match.id,
        listing_id=job.id,
        platform=job.platform,
        job_id=job.job_id,
        source_company=job.source_company,
        source_site=job.source_site,
        title=job.title,
        department=job.department,
        employment_type=job.employment_type,
        location_raw=job.location_raw,
        location_city=job.location_city,
        location_country=job.location_country,
        remote_type=job.remote_type,
        description_html=job.description_html,
        description_text=job.description_text,
        requirements_text=job.requirements_text,
        skills_extracted=job.skills_extracted,
        posted_at=job.posted_at,
        apply_url=job.apply_url,
        location_display="/".join(location_labels) if location_labels else "地点未知",
        location_cities=location_labels,
        location_options=location_options,
        is_merged=False,
        merged_count=1,
        salary_raw=job.salary_raw,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        lang=job.lang,
        crawl_time=job.crawl_time,
        apply_supported=bool(job.apply_url),
        rule_score=match.rule_score,
        llm_score=match.llm_score,
        final_score=match.final_score,
        highlights=match.highlights,
        missing_keywords=match.missing_keywords,
        risk_flags=match.risk_flags,
        llm_summary=match.llm_summary,
        cached_llm=match.cached_llm,
        analysis_provider=match.analysis_provider,
        analysis_degraded=match.analysis_degraded,
        analysis_notice=match.analysis_notice,
    )


def merged_match_response(
    match: JobMatch,
    job: JobListing,
    location_options: list[JobLocationOptionResponse],
) -> JobMatchResponse:
    normalized_options = location_options or [
        JobLocationOptionResponse(
            listing_id=job.id,
            location_city=job.location_city,
            location_raw=job.location_raw,
            apply_url=job.apply_url,
        )
    ]
    location_labels = list(
        dict.fromkeys(
            (
                option.location_city.strip()
                or option.location_raw.strip()
                or "地点未知"
            )
            for option in normalized_options
        )
    )
    merged_count = max(1, len(normalized_options))
    return JobMatchResponse(
        id=match.id,
        listing_id=job.id,
        platform=job.platform,
        job_id=job.job_id,
        source_company=job.source_company,
        source_site=job.source_site,
        title=job.title,
        department=job.department,
        employment_type=job.employment_type,
        location_raw=job.location_raw,
        location_city=job.location_city,
        location_country=job.location_country,
        remote_type=job.remote_type,
        description_html=job.description_html,
        description_text=job.description_text,
        requirements_text=job.requirements_text,
        skills_extracted=job.skills_extracted,
        posted_at=job.posted_at,
        apply_url=job.apply_url,
        location_display="/".join(location_labels) if location_labels else "地点未知",
        location_cities=location_labels,
        location_options=normalized_options,
        is_merged=merged_count > 1,
        merged_count=merged_count,
        salary_raw=job.salary_raw,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        lang=job.lang,
        crawl_time=job.crawl_time,
        apply_supported=bool(job.apply_url),
        rule_score=match.rule_score,
        llm_score=match.llm_score,
        final_score=match.final_score,
        highlights=match.highlights,
        missing_keywords=match.missing_keywords,
        risk_flags=match.risk_flags,
        llm_summary=match.llm_summary,
        cached_llm=match.cached_llm,
        analysis_provider=match.analysis_provider,
        analysis_degraded=match.analysis_degraded,
        analysis_notice=match.analysis_notice,
    )


def _normalize_merge_text(value: str) -> str:
    if not value:
        return ""
    compact = re.sub(r"\s+", " ", value).strip().lower()
    # Drop punctuation noise so near-identical JD text produces a stable signature.
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", compact)


def _heuristic_merge_key(job: JobListing) -> tuple[str, str, str, str, str, str, str] | None:
    content_source = job.requirements_text or job.description_text or ""
    content_signature = _normalize_merge_text(content_source)[:240]
    if len(content_signature) < 20:
        return None

    title = _normalize_merge_text(job.title)
    if not title:
        return None

    return (
        job.platform.lower(),
        job.source_site.lower(),
        job.source_company.lower(),
        title,
        _normalize_merge_text(job.employment_type),
        _normalize_merge_text(job.department),
        content_signature,
    )


def attempt_response(attempt: ApplicationAttempt) -> ApplicationAttemptResponse:
    return ApplicationAttemptResponse(
        id=attempt.id,
        listing_id=attempt.job_id,
        platform=attempt.platform,
        mode=attempt.mode,
        status=attempt.status,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
        message=attempt.message,
        verification_url=attempt.verification_url,
        launch_url=attempt.launch_url,
        context=attempt.context or {},
    )


async def ensure_platform_search_ready(platform: str, db: SessionDep) -> None:
    adapter = platform_gateway.get(platform)
    capability = adapter.capability()
    if not capability.session_required:
        return
    state = await adapter.session_state(db)
    if not state.get("active"):
        raise HTTPException(
            status_code=409,
            detail=f"{platform} 需要先准备好可用会话后才能搜索。",
        )
    if not state.get("search_ready"):
        raise HTTPException(
            status_code=409,
            detail=f"{platform} 会话尚未准备完成。",
        )


@app.get("/api/app-state", response_model=AppStateResponse)
def get_app_state(db: SessionDep) -> AppStateResponse:
    return AppStateResponse(**compliance_service.app_state(db))


def official_sources_summary() -> str:
    variant_labels = {
        "experienced": "社招",
        "campus": "校招",
        "internship": "实习",
    }
    grouped: dict[str, list[str]] = {}
    for source in load_sources():
        grouped.setdefault(source.company_name, [])
        if source.variant not in grouped[source.company_name]:
            grouped[source.company_name].append(source.variant)
    if not grouped:
        return "代码清单：暂无来源"

    parts: list[str] = []
    for company_name, variants in grouped.items():
        labels = [variant_labels.get(variant, variant) for variant in variants]
        parts.append(f"{company_name}({' + '.join(labels)})")
    return "代码清单：" + "；".join(parts)


def runtime_config_response() -> RuntimeConfigResponse:
    llm_config = runtime_config_service.get_llm_config()
    llm_state = runtime_config_service.llm_runtime_state(llm_config)
    return RuntimeConfigResponse(
        api_port=settings.api_port,
        llm_provider=llm_config.llm_provider,
        llm_effective_provider=llm_state.effective_provider,
        llm_configured=llm_state.configured,
        llm_missing_envs=llm_state.missing_fields,
        llm_notice=llm_state.notice,
        openai_api_key_configured=bool(llm_config.openai_api_key),
        openai_api_key_preview=runtime_config_service.api_key_preview(
            llm_config.openai_api_key
        ),
        openai_base_url=llm_config.openai_base_url,
        openai_model=llm_config.openai_model,
        official_sources_summary=official_sources_summary(),
    )


@app.get("/api/runtime-config", response_model=RuntimeConfigResponse)
def get_runtime_config() -> RuntimeConfigResponse:
    return runtime_config_response()


@app.put("/api/runtime-config", response_model=RuntimeConfigResponse)
def update_runtime_config(payload: RuntimeConfigUpdateRequest) -> RuntimeConfigResponse:
    runtime_config_service.update_llm_config(
        llm_provider=payload.llm_provider,
        openai_base_url=payload.openai_base_url,
        openai_model=payload.openai_model,
        openai_api_key=payload.openai_api_key,
        replace_api_key=payload.replace_api_key,
    )
    return runtime_config_response()


@app.post("/api/runtime-config/llm/models", response_model=LLMModelListResponse)
async def list_runtime_models(payload: LLMRuntimeProbeRequest) -> LLMModelListResponse:
    config = runtime_config_service.merge_test_config(
        llm_provider=payload.llm_provider,
        openai_base_url=payload.openai_base_url,
        openai_model=payload.openai_model,
        openai_api_key=payload.openai_api_key,
        use_saved_api_key=payload.use_saved_api_key,
    )
    if config.llm_provider != "openai_compatible":
        raise HTTPException(
            status_code=400,
            detail="只有 OpenAI 兼容提供方支持拉取模型列表。",
        )

    llm_state = runtime_config_service.llm_runtime_state(config, require_model=False)
    if llm_state.missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"缺少必要配置：{', '.join(llm_state.missing_fields)}",
        )

    try:
        models = await runtime_config_service.list_models(config)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"获取模型列表失败: {error}") from error

    return LLMModelListResponse(
        provider=config.llm_provider,
        models=models,
        message=f"已获取 {len(models)} 个模型。",
    )


@app.post("/api/runtime-config/llm/test", response_model=LLMConnectionTestResponse)
async def test_runtime_llm(
    payload: LLMRuntimeProbeRequest,
) -> LLMConnectionTestResponse:
    config = runtime_config_service.merge_test_config(
        llm_provider=payload.llm_provider,
        openai_base_url=payload.openai_base_url,
        openai_model=payload.openai_model,
        openai_api_key=payload.openai_api_key,
        use_saved_api_key=payload.use_saved_api_key,
    )
    if config.llm_provider != "openai_compatible":
        raise HTTPException(
            status_code=400,
            detail="只有 OpenAI 兼容提供方支持测试连接。",
        )

    llm_state = runtime_config_service.llm_runtime_state(config)
    if llm_state.missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"缺少必要配置：{', '.join(llm_state.missing_fields)}",
        )

    try:
        result = await runtime_config_service.test_connection(config)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"模型连接测试失败: {error}") from error

    return LLMConnectionTestResponse(
        ok=True,
        provider=config.llm_provider,
        model=config.openai_model,
        latency_ms=result.get("latency_ms"),
        reply_preview=result.get("reply_preview"),
        message="模型连接测试通过。",
    )


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


@app.get("/api/sources")
def list_sources():
    sources = load_sources()
    return [
        {
            "key": source.key,
            "company_name": source.company_name,
            "variant": source.variant,
            "label": source.label,
        }
        for source in sources
    ]


@app.get("/api/sources/variants")
def list_source_variants():
    return get_available_variants()


@app.get("/api/sources/companies")
def list_source_companies():
    return get_available_companies()


@app.get("/api/platforms/{platform}/capabilities")
def get_platform_capabilities(platform: str):
    return platform_gateway.get(platform).capability()


@app.post("/api/platforms/{platform}/session/start", response_model=PlatformSessionResponse)
async def start_platform_session(platform: str, db: SessionDep):
    adapter = platform_gateway.get(platform)
    capability = adapter.capability()
    if not capability.session_supported:
        raise HTTPException(status_code=409, detail=f"{platform} 不使用独立会话。")
    await adapter.start_session(db)
    return platform_session_response(platform, await adapter.session_state(db))


@app.get("/api/platforms/{platform}/session", response_model=PlatformSessionResponse)
async def get_platform_session(platform: str, db: SessionDep):
    adapter = platform_gateway.get(platform)
    capability = adapter.capability()
    if not capability.session_supported:
        raise HTTPException(status_code=409, detail=f"{platform} 不使用独立会话。")
    return platform_session_response(platform, await adapter.session_state(db))


@app.post(
    "/api/platforms/{platform}/session/check-ready",
    response_model=PlatformSessionResponse,
)
async def check_platform_session_ready(platform: str, db: SessionDep):
    adapter = platform_gateway.get(platform)
    capability = adapter.capability()
    if not capability.session_supported:
        raise HTTPException(status_code=409, detail=f"{platform} 不使用独立会话。")
    return platform_session_response(platform, await adapter.session_state(db))


@app.get("/api/platforms/{platform}/risk-status", response_model=RiskStatusResponse)
def get_risk_status(platform: str, db: SessionDep):
    return RiskStatusResponse(**risk_control_service.current_status(db, platform))


@app.post("/api/search-sessions", response_model=SearchSessionResponse)
async def create_search_session(payload: SearchSessionCreate, db: SessionDep):
    platforms = list(dict.fromkeys(payload.platforms))
    if not platforms:
        platforms = ["official"]

    adapters = platform_gateway.resolve(platforms)
    for adapter in adapters:
        capability = adapter.capability()
        if not capability.selectable:
            raise HTTPException(
                status_code=409,
                detail=capability.disabled_reason or f"{adapter.platform} 当前不可用。",
            )
        if not capability.search_supported:
            raise HTTPException(status_code=409, detail=f"{adapter.platform} 不支持搜索。")
        if payload.mode == "review_in_browser" and not capability.review_open_supported:
            raise HTTPException(status_code=409, detail=f"{adapter.platform} 不支持打开职位页面查看。")
        if payload.mode == "guided_apply" and not capability.guided_apply_supported:
            raise HTTPException(status_code=409, detail=f"{adapter.platform} 不支持引导投递。")
        if (
            payload.mode == "guided_apply"
            and not compliance_service.has_guided_apply_consent(db, adapter.platform)
        ):
            raise HTTPException(
                status_code=403,
                detail=f"{adapter.platform} 需要先同意引导投递提示后才能继续。",
            )
        await ensure_platform_search_ready(adapter.platform, db)

    normalized_payload = SearchSessionCreate(
        platforms=platforms,
        mode=payload.mode,
        job_targets=payload.job_targets,
        cities=payload.cities,
        salary_floor=payload.salary_floor,
        must_have_keywords=payload.must_have_keywords,
        source_variants=payload.source_variants,
        source_companies=payload.source_companies,
        match_limit=payload.match_limit,
        company_job_limit=payload.company_job_limit,
        force_refresh=payload.force_refresh,
    )
    return await search_service.create_session(db, normalized_payload)


@app.get("/api/search-sessions", response_model=list[SearchSessionResponse])
def list_search_sessions(db: SessionDep):
    return db.exec(select(SearchSession).order_by(SearchSession.created_at.desc())).all()


@app.get("/api/search-sessions/{session_id}", response_model=SearchSessionResponse)
def get_search_session(session_id: str, db: SessionDep):
    session = db.get(SearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="未找到搜索任务。")
    return session


@app.post("/api/search-sessions/{session_id}/retry", response_model=SearchSessionResponse)
async def retry_search_session(session_id: str, db: SessionDep):
    return await search_service.retry_session(db, session_id)


@app.post(
    "/api/search-sessions/{session_id}/open-verification",
    response_model=VerificationWindowResponse,
)
async def open_search_verification(session_id: str, db: SessionDep):
    return VerificationWindowResponse(**(await search_service.reopen_verification(db, session_id)))


@app.get("/api/search-sessions/{session_id}/matches", response_model=list[JobMatchResponse])
def get_search_matches(session_id: str, db: SessionDep):
    session = db.get(SearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="未找到搜索任务。")
    match_limit = max(1, min(1000, session.match_limit or settings.search_match_limit))
    matches = db.exec(
        select(JobMatch)
        .where(JobMatch.session_id == session_id)
        .order_by(JobMatch.final_score.desc())
    ).all()
    jobs = {
        job.id: job
        for job in db.exec(select(JobListing).where(JobListing.session_id == session_id)).all()
    }
    grouped_index: dict[tuple[str, str, str, str], int] = {}
    heuristic_grouped_index: dict[tuple[str, str, str, str, str, str, str], int] = {}
    grouped_payload: list[dict] = []

    for match in matches:
        job = jobs.get(match.job_id)
        if not job:
            continue

        option = JobLocationOptionResponse(
            listing_id=job.id,
            location_city=job.location_city,
            location_raw=job.location_raw,
            apply_url=job.apply_url,
        )

        normalized_job_id = (job.job_id or "").strip()
        if not normalized_job_id:
            grouped_payload.append(
                {
                    "match": match,
                    "job": job,
                    "location_options": [option],
                    "location_option_keys": {
                        (
                            (option.location_city or option.location_raw).strip().lower(),
                            option.apply_url.strip().lower(),
                        )
                    },
                }
            )
            continue

        group_key = (
            job.platform.lower(),
            job.source_site.lower(),
            job.source_company.lower(),
            normalized_job_id.lower(),
        )
        heuristic_key = _heuristic_merge_key(job)

        existing_index = grouped_index.get(group_key)
        if existing_index is None and heuristic_key is not None:
            existing_index = heuristic_grouped_index.get(heuristic_key)
        option_key = (
            (option.location_city or option.location_raw).strip().lower(),
            option.apply_url.strip().lower(),
        )
        if existing_index is None:
            current_index = len(grouped_payload)
            grouped_index[group_key] = current_index
            if heuristic_key is not None:
                heuristic_grouped_index[heuristic_key] = current_index
            grouped_payload.append(
                {
                    "match": match,
                    "job": job,
                    "location_options": [option],
                    "location_option_keys": {option_key},
                }
            )
            continue

        existing = grouped_payload[existing_index]
        location_option_keys: set[tuple[str, str]] = existing["location_option_keys"]
        if option_key in location_option_keys:
            continue
        location_option_keys.add(option_key)
        location_options: list[JobLocationOptionResponse] = existing["location_options"]
        location_options.append(option)

    responses: list[JobMatchResponse] = []
    for payload in grouped_payload:
        responses.append(
            merged_match_response(
                payload["match"],
                payload["job"],
                payload["location_options"],
            )
        )
        if len(responses) >= match_limit:
            break
    return responses


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
        raise HTTPException(status_code=404, detail="未找到职位。")
    adapter = platform_gateway.get(job.platform)
    capability = adapter.capability()
    if not capability.review_open_supported:
        raise HTTPException(status_code=409, detail=f"{job.platform} 不支持打开职位页面查看。")
    message = await adapter.open_review(job.apply_url)
    return {"message": message}


@app.post("/api/jobs/{job_id}/guided-apply", response_model=ApplicationAttemptResponse)
async def guided_apply(job_id: str, db: SessionDep):
    job = db.get(JobListing, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="未找到职位。")
    adapter = platform_gateway.get(job.platform)
    capability = adapter.capability()
    if not capability.guided_apply_supported:
        raise HTTPException(status_code=409, detail=f"{job.platform} 不支持引导投递。")
    if not compliance_service.has_guided_apply_consent(db, job.platform):
        raise HTTPException(status_code=403, detail=f"{job.platform} 需要先同意引导投递提示后才能继续。")

    risk_control_service.ensure_guided_apply_allowed(db, job.platform)
    profile = profile_service.load_or_create(db)
    if not profile.source_filename:
        raise HTTPException(status_code=409, detail="开始引导投递前请先上传简历。")

    attempt = ApplicationAttempt(
        job_id=job.id,
        platform=job.platform,
        mode="guided_apply",
        status="running",
        message="正在准备官网引导投递流程。",
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    try:
        outcome = await adapter.guided_apply(job, profile)
        attempt.status = outcome.status
        attempt.message = outcome.message
        attempt.verification_url = outcome.verification_url
        attempt.launch_url = outcome.launch_url
        attempt.context = outcome.context
        attempt.updated_at = datetime.utcnow()
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        return attempt_response(attempt)
    except Exception as error:
        attempt.status = "failed"
        attempt.message = str(error)
        attempt.updated_at = datetime.utcnow()
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/application-attempts", response_model=list[ApplicationAttemptResponse])
def list_application_attempts(db: SessionDep):
    attempts = db.exec(
        select(ApplicationAttempt).order_by(ApplicationAttempt.created_at.desc())
    ).all()
    return [attempt_response(attempt) for attempt in attempts]


@app.get("/api/application-attempts/{attempt_id}", response_model=ApplicationAttemptResponse)
def get_application_attempt(attempt_id: str, db: SessionDep):
    attempt = db.get(ApplicationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="未找到投递记录。")
    return attempt_response(attempt)


@app.post(
    "/api/application-attempts/{attempt_id}/open-verification-window",
    response_model=VerificationWindowResponse,
)
def open_application_attempt_verification(attempt_id: str, db: SessionDep):
    attempt = db.get(ApplicationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="未找到投递记录。")
    if not attempt.verification_url:
        raise HTTPException(status_code=409, detail="当前投递不需要验证。")
    attempt.updated_at = datetime.utcnow()
    db.add(attempt)
    db.commit()
    return VerificationWindowResponse(
        url=attempt.verification_url,
        title=f"{attempt.platform} 验证",
        message="请在应用内弹窗完成官网登录或验证码，然后继续投递。",
    )


@app.post(
    "/api/application-attempts/{attempt_id}/continue",
    response_model=ApplicationAttemptResponse,
)
def continue_application_attempt(attempt_id: str, db: SessionDep):
    attempt = db.get(ApplicationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="未找到投递记录。")
    if attempt.status != "needs_verification":
        raise HTTPException(status_code=409, detail="当前投递不处于等待验证状态。")

    attempt.status = "prepared"
    attempt.message = (
        "验证窗口已关闭，官网投递流程可以继续。"
    )
    attempt.updated_at = datetime.utcnow()
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt_response(attempt)


@app.post("/api/application-attempts/{attempt_id}/cancel", response_model=ApplicationAttemptResponse)
def cancel_application_attempt(attempt_id: str, db: SessionDep):
    attempt = db.get(ApplicationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="未找到投递记录。")
    attempt.status = "cancelled"
    attempt.updated_at = datetime.utcnow()
    attempt.message = "已由用户取消。"
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt_response(attempt)


@app.post("/api/emergency-stop")
def set_emergency_stop(payload: EmergencyStopRequest, db: SessionDep):
    return risk_control_service.set_emergency_stop(db, payload.active)
