from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Protocol

import httpx
from sqlmodel import Session

from ..models import CandidateProfile, JobListing, LLMAnalysisCache
from .runtime_config import LLMRuntimeConfig, runtime_config_service


@dataclass
class AnalysisMetadata:
    provider: str
    degraded: bool
    notice: str | None


@dataclass
class LLMResult:
    cache_key: str
    external_job_id: str
    llm_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]
    llm_summary: str
    cached: bool = False
    analysis_provider: str = "heuristic"
    analysis_degraded: bool = False
    analysis_notice: str | None = None


@dataclass
class AnalysisBatch:
    metadata: AnalysisMetadata
    results: list[LLMResult]


class LLMConfigurationError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    metadata: AnalysisMetadata

    async def analyze(
        self,
        profile: CandidateProfile,
        jobs: Iterable[JobListing],
    ) -> list[LLMResult]: ...

    def cache_key(self, platform: str, external_job_id: str, jd_hash: str) -> str: ...


class HeuristicLLMProvider:
    name = "heuristic"

    def __init__(self, *, notice: str | None) -> None:
        self.metadata = AnalysisMetadata(
            provider=self.name,
            degraded=True,
            notice=notice
            or "Using heuristic analysis only. Configure an OpenAI-compatible model for full ranking.",
        )

    def cache_key(self, platform: str, external_job_id: str, jd_hash: str) -> str:
        value = f"{self.name}:{platform}:{external_job_id}:{jd_hash}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

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
            role_bonus = 8 if any(role in job.title.lower() for role in target_roles) else 0
            score = min(100.0, 55.0 + len(overlap) * 7 + role_bonus - len(missing) * 4)

            risk_flags: list[str] = []
            if job.salary_min and profile.salary_floor and job.salary_min < profile.salary_floor:
                risk_flags.append("salary below target")
            if "leader" in job.jd_text.lower() or "带团队" in job.jd_text:
                risk_flags.append("management responsibility")
            if "onsite" in job.work_mode.lower():
                risk_flags.append("onsite preference")

            summary = (
                f"Matched on {', '.join(overlap[:4]) or 'general engineering fit'}. "
                f"Watch for {', '.join((missing + risk_flags)[:3]) or 'no major hard blockers detected'}."
            )
            results.append(
                LLMResult(
                    cache_key=self.cache_key(job.platform, job.external_job_id, job.jd_hash),
                    external_job_id=job.external_job_id,
                    llm_score=score,
                    highlights=overlap[:5] or list(candidate_keywords)[:3],
                    missing_keywords=missing[:4],
                    risk_flags=risk_flags[:4],
                    llm_summary=summary,
                    analysis_provider=self.metadata.provider,
                    analysis_degraded=self.metadata.degraded,
                    analysis_notice=self.metadata.notice,
                )
            )
        return results


class OpenAICompatibleLLMProvider:
    name = "openai_compatible"

    def __init__(self, config: LLMRuntimeConfig) -> None:
        self.config = config
        self.metadata = AnalysisMetadata(
            provider=self.name,
            degraded=False,
            notice=None,
        )

    def cache_key(self, platform: str, external_job_id: str, jd_hash: str) -> str:
        value = (
            f"{self.name}:{self.config.openai_base_url}:{self.config.openai_model}:"
            f"{platform}:{external_job_id}:{jd_hash}"
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _build_prompt(self, profile: CandidateProfile, jobs: list[JobListing]) -> list[dict]:
        profile_blob = {
            "headline": profile.headline,
            "summary": profile.summary[:1000],
            "target_roles": profile.target_roles,
            "preferred_cities": profile.preferred_cities,
            "salary_floor": profile.salary_floor,
            "years_experience": profile.years_experience,
            "skills": profile.skills,
            "must_have_keywords": profile.must_have_keywords,
        }
        jobs_blob = [
            {
                "external_job_id": job.external_job_id,
                "platform": job.platform,
                "title": job.title,
                "company_name": job.company_name,
                "city": job.city,
                "salary_text": job.salary_text,
                "work_mode": job.work_mode,
                "jd_text": job.jd_text[:3000],
            }
            for job in jobs
        ]
        instruction = (
            "You are ranking official career-site job listings for a candidate. "
            "Return strict JSON with shape "
            "{\"results\": [{\"external_job_id\": str, \"llm_score\": number, "
            "\"highlights\": [str], \"missing_keywords\": [str], "
            "\"risk_flags\": [str], \"llm_summary\": str}]}. "
            "Scores must be 0-100. Only use information present in the candidate profile and JD."
        )
        return [
            {"role": "system", "content": instruction},
            {
                "role": "user",
                "content": json.dumps(
                    {"profile": profile_blob, "jobs": jobs_blob},
                    ensure_ascii=False,
                ),
            },
        ]

    @staticmethod
    def _extract_json(text: str) -> dict:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Model response did not contain JSON.")
        return json.loads(text[start : end + 1])

    async def analyze(
        self,
        profile: CandidateProfile,
        jobs: Iterable[JobListing],
    ) -> list[LLMResult]:
        job_list = list(jobs)
        payload = {
            "model": self.config.openai_model,
            "messages": self._build_prompt(profile, job_list),
            "temperature": 0.2,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.openai_api_key}",
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{self.config.openai_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = self._extract_json(content)
        items = parsed.get("results", [])
        results_by_job = {item.get("external_job_id"): item for item in items if item.get("external_job_id")}

        results: list[LLMResult] = []
        for job in job_list:
            item = results_by_job.get(job.external_job_id, {})
            llm_score = float(item.get("llm_score", 65.0))
            highlights = [str(value) for value in item.get("highlights", [])][:5]
            missing = [str(value) for value in item.get("missing_keywords", [])][:4]
            risk_flags = [str(value) for value in item.get("risk_flags", [])][:4]
            summary = str(item.get("llm_summary", "")).strip() or "Model ranked this role from the cleaned official JD."
            results.append(
                LLMResult(
                    cache_key=self.cache_key(job.platform, job.external_job_id, job.jd_hash),
                    external_job_id=job.external_job_id,
                    llm_score=max(0.0, min(100.0, llm_score)),
                    highlights=highlights,
                    missing_keywords=missing,
                    risk_flags=risk_flags,
                    llm_summary=summary,
                    analysis_provider=self.metadata.provider,
                    analysis_degraded=self.metadata.degraded,
                    analysis_notice=self.metadata.notice,
                )
            )
        return results


class LLMService:
    def _primary_provider(self) -> LLMProvider:
        llm_config = runtime_config_service.get_llm_config()
        llm_state = runtime_config_service.llm_runtime_state(llm_config)
        if llm_config.llm_provider == "openai_compatible":
            if llm_state.configured:
                return OpenAICompatibleLLMProvider(llm_config)
            raise LLMConfigurationError(llm_state.notice)
        return HeuristicLLMProvider(notice=llm_state.notice)

    def _cached_results(
        self,
        db: Session,
        provider: LLMProvider,
        jobs: list[JobListing],
    ) -> tuple[list[LLMResult], list[JobListing]]:
        results: list[LLMResult] = []
        fresh_jobs: list[JobListing] = []
        for job in jobs:
            cache_key = provider.cache_key(job.platform, job.external_job_id, job.jd_hash)
            cached = db.get(LLMAnalysisCache, cache_key)
            if not cached:
                fresh_jobs.append(job)
                continue
            results.append(
                LLMResult(
                    cache_key=cache_key,
                    external_job_id=job.external_job_id,
                    llm_score=cached.llm_score,
                    highlights=list(cached.highlights),
                    missing_keywords=list(cached.missing_keywords),
                    risk_flags=list(cached.risk_flags),
                    llm_summary=cached.llm_summary,
                    cached=True,
                    analysis_provider=provider.metadata.provider,
                    analysis_degraded=provider.metadata.degraded,
                    analysis_notice=provider.metadata.notice,
                )
            )
        return results, fresh_jobs

    def _persist_results(
        self,
        db: Session,
        provider: LLMProvider,
        jobs: list[JobListing],
        results: list[LLMResult],
    ) -> None:
        for job, result in zip(jobs, results, strict=True):
            cache = LLMAnalysisCache(
                cache_key=result.cache_key,
                provider=provider.metadata.provider,
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

    async def analyze_jobs(
        self,
        db: Session,
        profile: CandidateProfile,
        jobs: list[JobListing],
    ) -> AnalysisBatch:
        if not jobs:
            metadata = self._primary_provider().metadata
            return AnalysisBatch(metadata=metadata, results=[])

        provider = self._primary_provider()
        cached_results, fresh_jobs = self._cached_results(db, provider, jobs)
        fresh_results = await provider.analyze(profile, fresh_jobs) if fresh_jobs else []
        if fresh_results:
            self._persist_results(db, provider, fresh_jobs, fresh_results)
        return AnalysisBatch(
            metadata=provider.metadata,
            results=cached_results + fresh_results,
        )


llm_service = LLMService()
