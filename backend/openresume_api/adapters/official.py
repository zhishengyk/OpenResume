from __future__ import annotations

import webbrowser

from sqlmodel import Session

from ..career_collectors import career_collector_runner, filter_sources, load_sources
from ..config import settings
from ..models import CandidateProfile, JobListing
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.rules import rule_pack_service
from .base import GuidedApplyOutcome, NormalizedJobDraft, PlatformDataError


def _draft_from_record(record) -> NormalizedJobDraft:
    return NormalizedJobDraft(
        source_company=record.source_company,
        source_site=record.source_site,
        job_id=record.job_id,
        title=record.title,
        department=record.department,
        employment_type=record.employment_type,
        location_raw=record.location_raw,
        location_city=record.location_city,
        location_country=record.location_country,
        remote_type=record.remote_type,
        description_html=record.description_html,
        description_text=record.description_text,
        requirements_text=record.requirements_text,
        skills_extracted=list(record.skills_extracted),
        posted_at=record.posted_at,
        apply_url=record.apply_url,
        salary_raw=record.salary_raw,
        salary_min=record.salary_min,
        salary_max=record.salary_max,
        lang=record.lang,
        crawl_time=record.crawl_time,
        raw_payload=dict(record.raw_payload or {}),
    )


def _connected_companies_text() -> str:
    companies = list(dict.fromkeys(source.company_name for source in load_sources()))
    return "、".join(companies) if companies else "暂无公司"


class OfficialAdapter:
    platform = "official"

    def __init__(self) -> None:
        self.last_run_stats: dict[str, int] = {}

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="招聘官网",
            search_supported=True,
            detail_parse_supported=True,
            review_open_supported=True,
            guided_apply_supported=True,
            session_supported=False,
            session_required=False,
            selectable=True,
            disabled_reason=None,
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        raise RuntimeError("官网搜索不需要单独启动浏览器会话。")

    async def session_state(self, db: Session) -> dict:
        return {
            "active": False,
            "search_ready": True,
            "storage_dir": "",
            "last_started_at": None,
        }

    async def search_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
        all_sources = load_sources()
        sources = filter_sources(
            all_sources,
            variants=search.source_variants or None,
            companies=search.source_companies or None,
        )
        if not sources:
            raise PlatformDataError("请至少选择一个招聘类型或公司。")
        run_results = await career_collector_runner.run(list(sources), search, profile)

        stats = {
            "sources_declared": len(sources),
            "sources_selected": len(sources),
            "collectors_executed": len(run_results),
            "sources_with_jobs": 0,
            "sources_empty": 0,
            "sources_not_implemented": 0,
            "source_errors": 0,
            "jobs_before_dedupe": 0,
            "jobs_after_dedupe": 0,
        }

        drafts: list[NormalizedJobDraft] = []
        for result in run_results:
            if result.status == "error":
                stats["source_errors"] += 1
                continue
            if result.status == "not_implemented":
                stats["sources_not_implemented"] += 1
                continue
            if result.jobs:
                stats["sources_with_jobs"] += 1
            else:
                stats["sources_empty"] += 1
            drafts.extend(_draft_from_record(job) for job in result.jobs)

        stats["jobs_before_dedupe"] = len(drafts)
        deduped: dict[tuple[str, str, str, str], NormalizedJobDraft] = {}
        for draft in drafts:
            key = (
                draft.source_site.lower(),
                draft.job_id.lower(),
                draft.title.lower(),
                draft.apply_url.lower(),
            )
            if not draft.job_id:
                key = (
                    draft.source_company.lower(),
                    draft.title.lower(),
                    draft.location_raw.lower(),
                    draft.apply_url.lower(),
                )
            deduped[key] = draft

        results = list(deduped.values())
        stats["jobs_after_dedupe"] = len(results)
        self.last_run_stats = stats
        if not results:
            raise PlatformDataError(
                f"当前没有任何已接入公司返回职位。当前来源：{_connected_companies_text()}。"
            )
        return results

    async def open_review(self, url: str) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        return "已打开官网职位页面。"

    async def guided_apply(
        self,
        job: JobListing,
        profile: CandidateProfile,
    ) -> GuidedApplyOutcome:
        if not profile.source_filename:
            raise RuntimeError("开始引导投递前请先上传简历。")
        verification_url = job.apply_url
        return GuidedApplyOutcome(
            status="needs_verification",
            message="请在应用内验证窗口完成官网登录或验证码，再继续本次投递。",
            verification_url=verification_url,
            launch_url=verification_url,
            context={
                "source_company": job.source_company,
                "job_id": job.job_id,
                "job_title": job.title,
                "resume_filename": profile.source_filename,
                "requires_popup": True,
            },
        )


official_adapter = OfficialAdapter()
