from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Protocol

import httpx
from sqlmodel import Session

from ..models import CandidateProfile, JobListing, LLMAnalysisCache
from .profile import profile_service
from .runtime_config import LLMRuntimeConfig, runtime_config_service


@dataclass
class AnalysisMetadata:
    provider: str
    degraded: bool
    notice: str | None


@dataclass
class LLMResult:
    cache_key: str
    job_id: str
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


def job_content_hash(job: JobListing) -> str:
    payload = "\n".join(
        [
            job.source_site,
            job.job_id,
            job.title,
            job.description_text,
            job.requirements_text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMProvider(Protocol):
    name: str
    metadata: AnalysisMetadata

    async def analyze(
        self,
        profile: CandidateProfile,
        jobs: Iterable[JobListing],
    ) -> list[LLMResult]: ...

    def cache_key(
        self,
        platform: str,
        source_site: str,
        job_id: str,
        content_hash: str,
        profile_signature: str,
    ) -> str: ...


class HeuristicLLMProvider:
    name = "heuristic"

    def __init__(self, *, notice: str | None) -> None:
        self.metadata = AnalysisMetadata(
            provider=self.name,
            degraded=True,
            notice=notice
            or "Current ranking uses heuristic analysis. Configure an OpenAI-compatible model to enable richer scoring.",
        )

    def cache_key(
        self,
        platform: str,
        source_site: str,
        job_id: str,
        content_hash: str,
        profile_signature: str,
    ) -> str:
        value = (
            f"{self.name}:{platform}:{source_site}:{job_id}:{content_hash}:"
            f"{profile_signature}"
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    async def analyze(
        self,
        profile: CandidateProfile,
        jobs: Iterable[JobListing],
    ) -> list[LLMResult]:
        results: list[LLMResult] = []
        target_roles = {role.lower() for role in profile.target_roles}
        project_terms = profile_service.project_evidence_terms(profile)
        award_terms = profile_service.award_evidence_terms(profile)
        signature = profile_service.profile_signature(profile)

        for job in jobs:
            combined_text = "\n".join(
                [job.title, job.description_text, job.requirements_text]
            ).lower()
            overlap = sorted(
                {
                    term
                    for term in (
                        profile.skills
                        + profile.must_have_keywords
                        + profile.tech_stack
                        + project_terms
                        + award_terms
                    )
                    if term.lower() in combined_text
                }
            )
            missing = sorted(
                {
                    keyword
                    for keyword in profile.must_have_keywords + profile.tech_stack[:2]
                    if keyword.lower() not in combined_text
                }
            )
            role_bonus = (
                8
                if any(
                    role in job.title.lower() or role in combined_text
                    for role in target_roles
                )
                else 0
            )
            score = min(100.0, 55.0 + len(overlap) * 6 + role_bonus - len(missing) * 4)

            risk_flags: list[str] = []
            if job.salary_min and profile.salary_floor and job.salary_min < profile.salary_floor:
                risk_flags.append("Salary below expectation")
            if "leader" in combined_text or "team lead" in combined_text:
                risk_flags.append("May include people management")
            if job.remote_type.lower() == "onsite":
                risk_flags.append("Onsite work required")

            summary = (
                f"Strong overlap: {', '.join(overlap[:4]) or 'general role direction'}; "
                f"watchouts: {', '.join((missing + risk_flags)[:3]) or 'no major blockers found'}."
            )
            results.append(
                LLMResult(
                    cache_key=self.cache_key(
                        job.platform,
                        job.source_site,
                        job.job_id,
                        job_content_hash(job),
                        signature,
                    ),
                    job_id=job.job_id,
                    llm_score=score,
                    highlights=overlap[:5],
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

    def cache_key(
        self,
        platform: str,
        source_site: str,
        job_id: str,
        content_hash: str,
        profile_signature: str,
    ) -> str:
        value = (
            f"{self.name}:{self.config.openai_base_url}:{self.config.openai_model}:"
            f"{platform}:{source_site}:{job_id}:{content_hash}:{profile_signature}"
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _build_prompt(
        self,
        profile: CandidateProfile,
        jobs: list[JobListing],
    ) -> list[dict]:
        profile_blob = {
            "headline": profile.headline,
            "summary": profile.summary[:1000],
            "target_roles": profile.target_roles,
            "preferred_cities": profile.preferred_cities,
            "salary_floor": profile.salary_floor,
            "years_experience": profile.years_experience,
            "skills": profile.skills,
            "must_have_keywords": profile.must_have_keywords,
            "tech_stack": profile.tech_stack,
            "project_experiences": profile.project_experiences,
            "awards": profile.awards,
        }
        jobs_blob = [
            {
                "job_id": job.job_id,
                "platform": job.platform,
                "source_company": job.source_company,
                "source_site": job.source_site,
                "title": job.title,
                "department": job.department,
                "employment_type": job.employment_type,
                "location_city": job.location_city,
                "location_country": job.location_country,
                "remote_type": job.remote_type,
                "salary_raw": job.salary_raw,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "description_text": job.description_text[:2200],
                "requirements_text": job.requirements_text[:2200],
                "skills_extracted": job.skills_extracted,
            }
            for job in jobs
        ]
        instruction = (
            "You are ranking official career-site job listings for a candidate. "
            "Return strict JSON with shape "
            '{"results": [{"job_id": str, "llm_score": number, '
            '"highlights": [str], "missing_keywords": [str], '
            '"risk_flags": [str], "llm_summary": str}]}. '
            "Scores must be 0-100. Only use information present in the candidate profile and cleaned job payload. "
            "Do not speculate about missing page data or invent fields."
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

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = self._extract_json(content)
        items = parsed.get("results", [])
        results_by_job = {
            item.get("job_id"): item for item in items if item.get("job_id")
        }
        signature = profile_service.profile_signature(profile)

        results: list[LLMResult] = []
        for job in job_list:
            item = results_by_job.get(job.job_id, {})
            llm_score = float(item.get("llm_score", 65.0))
            highlights = [str(value) for value in item.get("highlights", [])][:5]
            missing = [str(value) for value in item.get("missing_keywords", [])][:4]
            risk_flags = [str(value) for value in item.get("risk_flags", [])][:4]
            summary = (
                str(item.get("llm_summary", "")).strip()
                or "Model ranked this role from the cleaned official payload."
            )
            results.append(
                LLMResult(
                    cache_key=self.cache_key(
                        job.platform,
                        job.source_site,
                        job.job_id,
                        job_content_hash(job),
                        signature,
                    ),
                    job_id=job.job_id,
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
        profile: CandidateProfile,
        jobs: list[JobListing],
    ) -> tuple[list[LLMResult], list[JobListing]]:
        results: list[LLMResult] = []
        fresh_jobs: list[JobListing] = []
        signature = profile_service.profile_signature(profile)
        for job in jobs:
            content_hash = job_content_hash(job)
            cache_key = provider.cache_key(
                job.platform,
                job.source_site,
                job.job_id,
                content_hash,
                signature,
            )
            cached = db.get(LLMAnalysisCache, cache_key)
            if not cached:
                fresh_jobs.append(job)
                continue
            results.append(
                LLMResult(
                    cache_key=cache_key,
                    job_id=job.job_id,
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
                source_site=job.source_site,
                job_id=job.job_id,
                content_hash=job_content_hash(job),
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
        cached_results, fresh_jobs = self._cached_results(db, provider, profile, jobs)

        fresh_results: list[LLMResult] = []
        final_metadata = provider.metadata
        if fresh_jobs:
            try:
                fresh_results = await provider.analyze(profile, fresh_jobs)
                if fresh_results:
                    self._persist_results(db, provider, fresh_jobs, fresh_results)
            except Exception as error:
                fallback = HeuristicLLMProvider(
                    notice=f"LLM call failed, falling back to heuristic analysis: {error}"
                )
                fresh_results = await fallback.analyze(profile, fresh_jobs)
                for result in fresh_results:
                    result.analysis_degraded = True
                    result.analysis_notice = fallback.metadata.notice
                final_metadata = fallback.metadata

        return AnalysisBatch(
            metadata=final_metadata,
            results=cached_results + fresh_results,
        )


llm_service = LLMService()
