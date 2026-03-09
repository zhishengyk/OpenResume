from __future__ import annotations

import asyncio
from dataclasses import dataclass
import webbrowser

import httpx
from sqlmodel import Session

from ..config import settings
from ..models import CandidateProfile, JobListing
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.official_sources import OfficialSource, official_source_service
from ..services.rules import rule_pack_service
from .base import GuidedApplyOutcome, NormalizedJobDraft, PlatformDataError
from .official_extractors import EXTRACTOR_REGISTRY, ExtractedCandidate, FetchPage, OfficialExtractor
from .official_extractors.common import (
    canonicalize_url,
    candidate_detail_key,
    candidate_quality_penalty,
    classification_from_text,
    compute_quality,
    detail_sections_blob,
    experience_text,
    extract_city,
    extract_salary,
    final_dedupe_key,
    merge_candidates,
    normalize_city,
    normalize_title,
    raw_payload_snapshot,
    stable_external_job_id,
    stable_jd_hash,
    work_mode,
)


@dataclass
class SourceExtractionResult:
    source: OfficialSource
    extractor: str
    entry_url: str
    candidates: list[ExtractedCandidate]


class OfficialAdapter:
    platform = "official"

    def __init__(self) -> None:
        self.last_run_stats: dict[str, int] = {}

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="Official career sites",
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
        raise RuntimeError("Official site search does not require a dedicated session.")

    async def session_state(self, db: Session) -> dict:
        return {
            "active": False,
            "search_ready": True,
            "storage_dir": "",
            "last_started_at": None,
        }

    def _score_source(
        self,
        source: OfficialSource,
        payload: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> int:
        score = 0
        lowered = f"{source.company_name} {source.url}".lower()
        if any(role.lower() in lowered for role in payload.job_targets or profile.target_roles):
            score += 2
        if profile.years_experience >= 3 and "campus" not in lowered:
            score += 3
        if any(token in lowered for token in ("career", "careers", "jobs", "social")):
            score += 2
        if source.source_kind in {"moka", "feishu", "hotjob"}:
            score += 1
        return score

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> FetchPage:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return FetchPage(
            requested_url=url,
            final_url=str(response.url),
            text=response.text,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
        )

    def _hinted_extractor(self, source: OfficialSource) -> OfficialExtractor | None:
        return next(
            (extractor for extractor in EXTRACTOR_REGISTRY if extractor.name == source.source_kind),
            None,
        )

    def _pick_extractor(
        self,
        source: OfficialSource,
        page: FetchPage,
        preferred_name: str | None = None,
    ) -> OfficialExtractor:
        extractors = list(EXTRACTOR_REGISTRY)
        if preferred_name:
            extractors.sort(key=lambda extractor: extractor.name != preferred_name)
        for extractor in extractors:
            if extractor.matches(source, page):
                return extractor
        return extractors[-1]

    async def _source_candidates(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        payload: SearchSessionCreate,
    ) -> SourceExtractionResult:
        page = await self._fetch_page(client, source.url)
        hinted = self._hinted_extractor(source)
        if hinted is not None:
            page = await hinted.prepare_source_page(client, source, page)
        extractor = self._pick_extractor(
            source,
            page,
            preferred_name=hinted.name if hinted is not None else None,
        )
        candidates = extractor.extract_candidates(
            source=source,
            page=page,
            requested_targets=payload.job_targets,
            requested_cities=payload.cities,
        )

        deduped: dict[str, ExtractedCandidate] = {}
        for candidate in candidates:
            candidate.raw_payload["company_name"] = source.company_name
            candidate.raw_payload["platform"] = self.platform
            candidate.raw_payload["extractor"] = extractor.name
            candidate.raw_payload["entry_url"] = page.final_url
            key = candidate_detail_key(candidate)
            if not key:
                continue
            existing = deduped.get(key)
            deduped[key] = merge_candidates(existing, candidate) if existing else candidate

        return SourceExtractionResult(
            source=source,
            extractor=extractor.name,
            entry_url=page.final_url,
            candidates=list(deduped.values())[: settings.official_job_limit_per_source],
        )

    async def _enrich_candidate(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        candidate: ExtractedCandidate,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> NormalizedJobDraft | None:
        detail_page: FetchPage
        try:
            detail_page = await self._fetch_page(client, candidate.detail_url)
        except Exception:
            detail_page = FetchPage(
                requested_url=candidate.detail_url,
                final_url=candidate.detail_url,
                text="",
                status_code=0,
                content_type="",
            )

        detail_extractor = self._pick_extractor(
            source,
            detail_page,
            preferred_name=str(candidate.raw_payload.get("extractor") or ""),
        )
        detail_page = await detail_extractor.prepare_detail_page(client, source, candidate, detail_page)
        detail = detail_extractor.extract_detail(
            source=source,
            candidate=candidate,
            page=detail_page,
            requested_targets=requested_targets,
            requested_cities=requested_cities,
        )
        quality = compute_quality(candidate, detail)
        if quality["drop_reasons"]:
            return None

        canonical_detail_url = canonicalize_url(detail.fetched_url or candidate.detail_url)
        title = normalize_title(candidate.title)
        city = normalize_city(
            candidate.city
            if candidate.city and candidate.city != "Remote"
            else detail.location_text
            or extract_city(detail.text, requested_cities)
        )
        salary_text, salary_min, salary_max = (
            (candidate.salary_text, candidate.salary_min, candidate.salary_max)
            if candidate.salary_text
            else extract_salary(detail.text)
        )
        jd_text = detail.text[:8000] or candidate.snippet or title
        apply_url = canonicalize_url(detail.apply_url or candidate.apply_url or canonical_detail_url)
        apply_requires_login = any(
            token in (apply_url or "").lower()
            for token in ("login", "signin", "passport", "account", "apply", "moka", "feishu", "hotjob")
        )
        raw_payload = raw_payload_snapshot(candidate, detail)
        raw_payload.update(
            {
                "platform": self.platform,
                "company_name": source.company_name,
                "extractor": detail_extractor.name,
                "quality": quality,
                "detail_sections": detail_sections_blob(detail),
            }
        )
        return NormalizedJobDraft(
            external_job_id=stable_external_job_id(
                source.company_name,
                title,
                city,
                canonical_detail_url,
            ),
            title=title,
            company_name=source.company_name,
            city=city or "Remote",
            salary_text=salary_text,
            salary_min=salary_min,
            salary_max=salary_max,
            experience_text=detail.experience_text or candidate.experience_text or experience_text(detail.text),
            degree_text=detail.degree_text or candidate.degree_text,
            work_mode=candidate.work_mode or work_mode(detail.text),
            url=canonical_detail_url,
            detail_url=canonical_detail_url,
            apply_url=apply_url,
            source_company_url=canonicalize_url(source.url),
            apply_requires_login=apply_requires_login,
            jd_text=jd_text,
            jd_hash=stable_jd_hash(jd_text, raw_payload.get("detail_sections") or {}),
            raw_payload=raw_payload,
        )

    async def search_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
        sources = list(official_source_service.load_sources())
        if not sources:
            raise PlatformDataError("No official source file could be loaded.")

        sources.sort(
            key=lambda item: self._score_source(item, search, profile),
            reverse=True,
        )
        selected_sources = sources[: settings.official_source_limit]
        stats = {
            "sources_selected": len(selected_sources),
            "entry_candidates": 0,
            "hard_filtered": 0,
            "detail_dropped": 0,
            "quality_penalized": 0,
            "final_model_candidates": 0,
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        }
        drafts: list[NormalizedJobDraft] = []
        async with httpx.AsyncClient(
            timeout=settings.official_request_timeout_seconds,
            headers=headers,
        ) as client:
            source_results = await asyncio.gather(
                *[
                    self._source_candidates(client, source, search)
                    for source in selected_sources
                ],
                return_exceptions=True,
            )
            for source, result in zip(selected_sources, source_results, strict=True):
                if isinstance(result, Exception):
                    continue
                filtered_candidates: list[ExtractedCandidate] = []
                for candidate in result.candidates:
                    if candidate.raw_payload.get("hard_filter_reasons"):
                        stats["hard_filtered"] += 1
                        continue
                    filtered_candidates.append(candidate)
                stats["entry_candidates"] += len(filtered_candidates)
                if not filtered_candidates:
                    continue

                enriched = await asyncio.gather(
                    *[
                        self._enrich_candidate(
                            client,
                            source,
                            candidate,
                            search.job_targets,
                            search.cities,
                        )
                        for candidate in filtered_candidates
                    ],
                    return_exceptions=True,
                )
                for item in enriched:
                    if isinstance(item, Exception):
                        continue
                    if item is None:
                        stats["detail_dropped"] += 1
                        continue
                    drafts.append(item)

        deduped: dict[tuple[str, str, str, str], NormalizedJobDraft] = {}
        for draft in drafts:
            key = final_dedupe_key(
                draft.company_name,
                draft.title,
                draft.city,
                draft.detail_url or draft.url,
            )
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = draft
                continue
            existing_score = int(existing.raw_payload.get("quality", {}).get("score") or 0)
            current_score = int(draft.raw_payload.get("quality", {}).get("score") or 0)
            deduped[key] = draft if current_score > existing_score else existing

        results = list(deduped.values())
        stats["quality_penalized"] = sum(
            1 for draft in results if candidate_quality_penalty(draft.raw_payload) > 0
        )
        stats["final_model_candidates"] = len(results)
        self.last_run_stats = stats
        if not results:
            raise PlatformDataError("No official jobs passed code-based cleaning.")
        return results

    async def open_review(self, url: str) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        return "Opened the official role page."

    async def guided_apply(
        self,
        job: JobListing,
        profile: CandidateProfile,
    ) -> GuidedApplyOutcome:
        if not profile.source_filename:
            raise RuntimeError("Upload a resume before starting guided apply.")
        verification_url = job.apply_url or job.detail_url or job.url
        return GuidedApplyOutcome(
            status="needs_verification",
            message=(
                "Open the in-app verification window, complete any login/captcha "
                "steps on the official site, then continue the attempt."
            ),
            verification_url=verification_url,
            launch_url=verification_url,
            context={
                "company_name": job.company_name,
                "job_title": job.title,
                "resume_filename": profile.source_filename,
                "requires_popup": True,
            },
        )


official_adapter = OfficialAdapter()
