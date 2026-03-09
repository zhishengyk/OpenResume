from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import re
import webbrowser
from urllib.parse import urljoin, urlparse

import httpx
from sqlmodel import Session

from ..config import settings
from ..models import CandidateProfile, JobListing
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.official_sources import OfficialSource, official_source_service
from ..services.rules import rule_pack_service
from .base import GuidedApplyOutcome, NormalizedJobDraft, PlatformDataError

COMMON_CITIES = [
    "Beijing",
    "Shanghai",
    "Hangzhou",
    "Shenzhen",
    "Guangzhou",
    "Suzhou",
    "Chengdu",
    "Nanjing",
    "Wuhan",
    "Xi'an",
    "北京",
    "上海",
    "杭州",
    "深圳",
    "广州",
    "苏州",
    "成都",
    "南京",
    "武汉",
    "西安",
]

JOB_TITLE_HINTS = [
    "engineer",
    "developer",
    "frontend",
    "backend",
    "full stack",
    "fullstack",
    "ai",
    "ml",
    "algorithm",
    "product",
    "designer",
    "test",
    "sre",
    "data",
    "工程师",
    "开发",
    "前端",
    "后端",
    "全栈",
    "算法",
    "测试",
    "产品",
    "设计",
    "数据",
]

NOISE_HINTS = [
    "about us",
    "campus guide",
    "faq",
    "policy",
    "brand",
    "contact",
    "news",
    "宣讲",
    "流程",
    "攻略",
    "常见问题",
    "品牌",
    "关于我们",
    "加入我们",
    "校招政策",
]


@dataclass
class ExtractedCandidate:
    title: str
    detail_url: str
    apply_url: str | None
    snippet: str
    company_url: str
    city: str
    salary_text: str
    salary_min: int
    salary_max: int
    experience_text: str
    degree_text: str
    work_mode: str
    raw_payload: dict


def _strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    value = re.sub(r"(?is)<style.*?>.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = value.replace("&nbsp;", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _normalize_text(value: str) -> str:
    value = re.sub(r"\[[^\]]+\]", " ", value)
    value = re.sub(r"【[^】]+】", " ", value)
    value = re.sub(r"#\d+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -|/")


def _normalize_city(value: str) -> str:
    candidate = value.strip()
    for separator in ("·", "-", "_", "/", "\\", " "):
        if separator in candidate:
            candidate = candidate.split(separator, 1)[0].strip()
    return candidate


def _extract_city(text: str, requested_cities: list[str]) -> str:
    for city in requested_cities:
        if city and city.lower() in text.lower():
            return _normalize_city(city)
    for city in COMMON_CITIES:
        if city.lower() in text.lower():
            return _normalize_city(city)
    return "Remote"


def _extract_salary(text: str) -> tuple[str, int, int]:
    match = re.search(r"(\d{1,2})\s*[kK]\s*[-~]\s*(\d{1,2})\s*[kK]", text)
    if not match:
        return "", 0, 0
    salary_min = int(match.group(1)) * 1000
    salary_max = int(match.group(2)) * 1000
    return match.group(0).upper(), salary_min, salary_max


def _looks_like_job(title: str, snippet: str, requested_targets: list[str]) -> bool:
    haystack = f"{title} {snippet}".lower()
    if any(noise in haystack for noise in NOISE_HINTS):
        return False
    if requested_targets and any(target.lower() in haystack for target in requested_targets):
        return True
    return any(keyword in haystack for keyword in JOB_TITLE_HINTS)


def _experience_text(text: str) -> str:
    match = re.search(r"(\d+\s*[-~]\s*\d+\s*(?:years|year|年))", text, re.I)
    if match:
        return match.group(1)
    return ""


def _degree_text(text: str) -> str:
    lowered = text.lower()
    if "master" in lowered or "硕士" in text:
        return "Master"
    if "bachelor" in lowered or "本科" in text:
        return "Bachelor"
    return ""


def _work_mode(text: str) -> str:
    lowered = text.lower()
    if "remote" in lowered or "远程" in text:
        return "remote"
    if "hybrid" in lowered or "混合" in text:
        return "hybrid"
    return "onsite"


def _stable_external_job_id(company_name: str, detail_url: str, title: str) -> str:
    raw = f"{company_name}|{detail_url}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _find_script_json_candidates(html: str) -> list[str]:
    scripts = re.findall(
        r'(?is)<script[^>]*?(?:type=["\']application/(?:ld\+json|json)["\'])?[^>]*>(.*?)</script>',
        html,
    )
    return [script.strip() for script in scripts if script.strip()]


def _walk_json_jobs(payload: object, company_url: str) -> list[ExtractedCandidate]:
    candidates: list[ExtractedCandidate] = []
    if isinstance(payload, dict):
        keys = {key.lower() for key in payload}
        title = payload.get("title") or payload.get("name") or payload.get("jobName")
        description = payload.get("description") or payload.get("jd") or payload.get("detail")
        url = payload.get("url") or payload.get("link") or payload.get("jobUrl")
        if (
            isinstance(title, str)
            and isinstance(url, str)
            and (isinstance(description, str) or isinstance(description, list))
            and {"title", "description"} & keys
        ):
            snippet = description if isinstance(description, str) else " ".join(description)
            salary_text, salary_min, salary_max = _extract_salary(snippet)
            candidates.append(
                ExtractedCandidate(
                    title=_normalize_text(title),
                    detail_url=urljoin(company_url, url),
                    apply_url=urljoin(company_url, url),
                    snippet=_strip_html(snippet)[:3000],
                    company_url=company_url,
                    city=_extract_city(snippet, []),
                    salary_text=salary_text,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    experience_text=_experience_text(snippet),
                    degree_text=_degree_text(snippet),
                    work_mode=_work_mode(snippet),
                    raw_payload={"source": "script-json", "payload": payload},
                )
            )
        for value in payload.values():
            candidates.extend(_walk_json_jobs(value, company_url))
    elif isinstance(payload, list):
        for item in payload:
            candidates.extend(_walk_json_jobs(item, company_url))
    return candidates


def _extract_anchor_candidates(
    html: str,
    source: OfficialSource,
    requested_targets: list[str],
    requested_cities: list[str],
) -> list[ExtractedCandidate]:
    candidates: list[ExtractedCandidate] = []
    pattern = re.compile(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>')
    for href, label_html in pattern.findall(html):
        detail_url = urljoin(source.url, href)
        parsed = urlparse(detail_url)
        if not parsed.scheme.startswith("http"):
            continue
        host = parsed.netloc.lower()
        if source.host not in host and not any(
            provider in host for provider in ("mokahr.com", "feishu.cn", "hotjob.cn", "zhiye.com")
        ):
            continue

        title = _normalize_text(_strip_html(label_html))
        snippet = title
        if not title or not _looks_like_job(title, snippet, requested_targets):
            continue

        salary_text, salary_min, salary_max = _extract_salary(snippet)
        candidates.append(
            ExtractedCandidate(
                title=title,
                detail_url=detail_url,
                apply_url=detail_url,
                snippet=snippet,
                company_url=source.url,
                city=_extract_city(snippet, requested_cities),
                salary_text=salary_text,
                salary_min=salary_min,
                salary_max=salary_max,
                experience_text=_experience_text(snippet),
                degree_text=_degree_text(snippet),
                work_mode=_work_mode(snippet),
                raw_payload={"source": "anchor", "href": href, "label": title},
            )
        )
    return candidates


class OfficialAdapter:
    platform = "official"

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

    async def _fetch_text(self, client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text

    async def _enrich_candidate(
        self,
        client: httpx.AsyncClient,
        candidate: ExtractedCandidate,
        requested_targets: list[str],
        requested_cities: list[str],
    ) -> NormalizedJobDraft | None:
        detail_html = ""
        try:
            detail_html = await self._fetch_text(client, candidate.detail_url)
        except Exception:
            detail_html = ""

        detail_text = _strip_html(detail_html) if detail_html else candidate.snippet
        title = _normalize_text(candidate.title)
        if not _looks_like_job(title, detail_text[:400], requested_targets):
            return None

        city = candidate.city if candidate.city != "Remote" else _extract_city(
            detail_text,
            requested_cities,
        )
        salary_text, salary_min, salary_max = (
            (candidate.salary_text, candidate.salary_min, candidate.salary_max)
            if candidate.salary_text
            else _extract_salary(detail_text)
        )
        jd_text = detail_text[:5000] or title
        apply_url = candidate.apply_url or candidate.detail_url
        apply_requires_login = any(
            token in (apply_url or "").lower()
            for token in ("login", "signin", "passport", "account", "apply", "moka", "feishu", "hotjob")
        )
        external_job_id = _stable_external_job_id(
            candidate.raw_payload.get("company_name", ""),
            candidate.detail_url,
            title,
        )
        return NormalizedJobDraft(
            external_job_id=external_job_id,
            title=title,
            company_name=candidate.raw_payload.get("company_name", "") or "",
            city=city,
            salary_text=salary_text,
            salary_min=salary_min,
            salary_max=salary_max,
            experience_text=candidate.experience_text or _experience_text(detail_text),
            degree_text=candidate.degree_text or _degree_text(detail_text),
            work_mode=candidate.work_mode or _work_mode(detail_text),
            url=candidate.detail_url,
            detail_url=candidate.detail_url,
            apply_url=apply_url,
            source_company_url=candidate.company_url,
            apply_requires_login=apply_requires_login,
            jd_text=jd_text,
            jd_hash=hashlib.md5(jd_text.encode("utf-8")).hexdigest(),
            raw_payload={
                **candidate.raw_payload,
                "platform": self.platform,
                "quality": {
                    "detail_page_found": bool(detail_html),
                    "structured_source": candidate.raw_payload.get("source") == "script-json",
                    "jd_length_ok": len(jd_text) >= 120,
                    "apply_url_found": bool(candidate.apply_url),
                },
            },
        )

    def _fallback_site_recommendation(
        self,
        source: OfficialSource,
        payload: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> NormalizedJobDraft:
        role = (payload.job_targets or profile.target_roles or ["Engineer"])[0]
        city = (payload.cities or profile.preferred_cities or ["Remote"])[0]
        jd_text = (
            f"Official hiring portal recommendation for {source.company_name}. "
            f"Preferred role: {role}. Preferred city: {city}. "
            f"Source kind: {source.source_kind}. Visit the official career site to inspect live roles."
        )
        external_job_id = _stable_external_job_id(source.company_name, source.url, role)
        return NormalizedJobDraft(
            external_job_id=external_job_id,
            title=f"{role} official hiring portal",
            company_name=source.company_name,
            city=city,
            salary_text="",
            salary_min=0,
            salary_max=0,
            experience_text="",
            degree_text="",
            work_mode="unknown",
            url=source.url,
            detail_url=source.url,
            apply_url=source.url,
            source_company_url=source.url,
            apply_requires_login=True,
            jd_text=jd_text,
            jd_hash=hashlib.md5(jd_text.encode("utf-8")).hexdigest(),
            raw_payload={
                "source": "official-site-fallback",
                "platform": self.platform,
                "source_kind": source.source_kind,
                "company_name": source.company_name,
                "quality": {
                    "detail_page_found": False,
                    "structured_source": False,
                    "jd_length_ok": True,
                    "apply_url_found": True,
                },
            },
        )

    async def _source_candidates(
        self,
        client: httpx.AsyncClient,
        source: OfficialSource,
        payload: SearchSessionCreate,
    ) -> list[ExtractedCandidate]:
        html = await self._fetch_text(client, source.url)
        extracted: list[ExtractedCandidate] = []

        for script_payload in _find_script_json_candidates(html):
            try:
                parsed = json.loads(script_payload)
            except Exception:
                continue
            for candidate in _walk_json_jobs(parsed, source.url):
                candidate.raw_payload["company_name"] = source.company_name
                candidate.raw_payload["platform"] = self.platform
                extracted.append(candidate)

        if not extracted:
            anchor_candidates = _extract_anchor_candidates(
                html,
                source,
                payload.job_targets,
                payload.cities,
            )
            for candidate in anchor_candidates:
                candidate.raw_payload["company_name"] = source.company_name
                candidate.raw_payload["platform"] = self.platform
            extracted.extend(anchor_candidates)

        deduped: dict[str, ExtractedCandidate] = {}
        for candidate in extracted:
            deduped.setdefault(candidate.detail_url, candidate)
        return list(deduped.values())[: settings.official_job_limit_per_source]

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
            tasks = [
                self._source_candidates(client, source, search)
                for source in selected_sources
            ]
            source_results = await asyncio.gather(*tasks, return_exceptions=True)
            for source, result in zip(selected_sources, source_results, strict=True):
                if isinstance(result, Exception):
                    drafts.append(self._fallback_site_recommendation(source, search, profile))
                    continue
                enriched = await asyncio.gather(
                    *[
                        self._enrich_candidate(client, candidate, search.job_targets, search.cities)
                        for candidate in result
                    ],
                    return_exceptions=True,
                )
                usable = [
                    item
                    for item in enriched
                    if isinstance(item, NormalizedJobDraft) and item.company_name
                ]
                if usable:
                    drafts.extend(usable)
                else:
                    drafts.append(self._fallback_site_recommendation(source, search, profile))

        deduped: dict[tuple[str, str, str], NormalizedJobDraft] = {}
        for draft in drafts:
            key = (
                draft.company_name.lower(),
                draft.title.lower(),
                (draft.detail_url or draft.url).lower(),
            )
            deduped.setdefault(key, draft)

        results = list(deduped.values())
        if not results:
            raise PlatformDataError("No official jobs could be extracted from the configured sources.")
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
