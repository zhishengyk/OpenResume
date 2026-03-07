from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from sqlmodel import Session

from ..models import CandidateProfile, JobListing, LLMAnalysisCache


@dataclass
class LLMResult:
    cache_key: str
    llm_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]
    llm_summary: str
    cached: bool = False


class HeuristicLLMProvider:
    async def analyze(
        self,
        profile: CandidateProfile,
        jobs: Iterable[JobListing],
    ) -> list[LLMResult]:
        results: list[LLMResult] = []
        candidate_keywords = {
            skill.lower() for skill in profile.skills + profile.must_have_keywords
        }
        target_roles = {role.lower() for role in profile.target_roles}

        for job in jobs:
            overlap = sorted(
                {
                    skill
                    for skill in profile.skills + profile.must_have_keywords
                    if skill.lower() in job.jd_text.lower()
                }
            )
            missing = sorted(
                {
                    keyword
                    for keyword in profile.must_have_keywords
                    if keyword.lower() not in job.jd_text.lower()
                }
            )
            role_bonus = (
                8 if any(role in job.title.lower() for role in target_roles) else 0
            )
            score = min(100.0, 55.0 + len(overlap) * 7 + role_bonus - len(missing) * 4)
            risk_flags = []
            if job.salary_min and profile.salary_floor and job.salary_min < profile.salary_floor:
                risk_flags.append("薪资低于预期")
            if "leader" in job.jd_text.lower() or "带团队" in job.jd_text:
                risk_flags.append("包含团队管理要求")
            if "onsite" in job.work_mode.lower():
                risk_flags.append("偏向线下坐班")

            summary = (
                f"核心匹配点集中在 {', '.join(overlap[:4]) or '基础工程能力'}；"
                f"需要留意 {', '.join((missing + risk_flags)[:3]) or '当前未发现明显硬伤'}。"
            )

            results.append(
                LLMResult(
                    cache_key=self.cache_key(job.platform, job.external_job_id, job.jd_hash),
                    llm_score=score,
                    highlights=overlap[:5] or list(candidate_keywords)[:3],
                    missing_keywords=missing[:4],
                    risk_flags=risk_flags[:4],
                    llm_summary=summary,
                )
            )

        return results

    @staticmethod
    def cache_key(platform: str, external_job_id: str, jd_hash: str) -> str:
        value = f"{platform}:{external_job_id}:{jd_hash}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class LLMService:
    def __init__(self) -> None:
        self.provider = HeuristicLLMProvider()

    async def analyze_jobs(
        self,
        db: Session,
        profile: CandidateProfile,
        jobs: list[JobListing],
    ) -> list[LLMResult]:
        fresh_jobs: list[JobListing] = []
        results: list[LLMResult] = []

        for job in jobs:
            key = self.provider.cache_key(job.platform, job.external_job_id, job.jd_hash)
            cached = db.get(LLMAnalysisCache, key)
            if cached:
                results.append(
                    LLMResult(
                        cache_key=key,
                        llm_score=cached.llm_score,
                        highlights=cached.highlights,
                        missing_keywords=cached.missing_keywords,
                        risk_flags=cached.risk_flags,
                        llm_summary=cached.llm_summary,
                        cached=True,
                    )
                )
            else:
                fresh_jobs.append(job)

        if fresh_jobs:
            fresh_results = await self.provider.analyze(profile, fresh_jobs)
            for result, job in zip(fresh_results, fresh_jobs, strict=True):
                cache = LLMAnalysisCache(
                    cache_key=result.cache_key,
                    platform=job.platform,
                    external_job_id=job.external_job_id,
                    jd_hash=job.jd_hash,
                    llm_score=result.llm_score,
                    highlights=result.highlights,
                    missing_keywords=result.missing_keywords,
                    risk_flags=result.risk_flags,
                    llm_summary=result.llm_summary,
                )
                db.merge(cache)
            db.commit()
            results.extend(fresh_results)

        return results


llm_service = LLMService()

