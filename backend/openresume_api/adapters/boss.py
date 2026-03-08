from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any
from urllib.parse import urlencode, urljoin
from sqlmodel import Session

from ..adapters.base import (
    NormalizedJobDraft,
    PlatformBlockedError,
    PlatformDataError,
)
from ..config import ROOT_DIR, settings
from ..models import CandidateProfile
from ..schemas import PlatformCapabilityResponse, SearchSessionCreate
from ..services.browser_session import browser_session_service
from ..services.rules import rule_pack_service


class BossAdapter:
    platform = "boss"
    base_url = "https://www.zhipin.com"
    search_page_url = f"{base_url}/web/geek/job"

    city_codes = {
        "\u5317\u4eac": "101010100",
        "\u4e0a\u6d77": "101020100",
        "\u5e7f\u5dde": "101280100",
        "\u6df1\u5733": "101280600",
        "\u676d\u5dde": "101210100",
        "\u82cf\u5dde": "101190400",
        "\u5357\u4eac": "101190100",
        "\u6210\u90fd": "101270100",
        "\u6b66\u6c49": "101200100",
        "\u897f\u5b89": "101110100",
        "\u91cd\u5e86": "101040100",
        "\u5929\u6d25": "101030100",
        "\u957f\u6c99": "101250100",
        "\u90d1\u5dde": "101180100",
        "\u5408\u80a5": "101220100",
        "\u53a6\u95e8": "101230200",
        "\u798f\u5dde": "101230100",
        "\u9752\u5c9b": "101120200",
        "\u6d4e\u5357": "101120100",
        "\u5b81\u6ce2": "101210400",
        "\u4e1c\u839e": "101281600",
        "\u4f5b\u5c71": "101280800",
        "\u73e0\u6d77": "101280700",
    }

    def __init__(self) -> None:
        fixtures_path = ROOT_DIR / "openresume_api" / "fixtures" / "boss_jobs.json"
        self.fixture_jobs = json.loads(fixtures_path.read_text(encoding="utf-8"))
        self.search_cache_dir = settings.cache_dir / "boss-search"
        self.search_cache_dir.mkdir(parents=True, exist_ok=True)

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="Boss \u76f4\u8058",
            search_supported=True,
            detail_parse_supported=True,
            review_open_supported=True,
            guided_apply_supported=True,
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        await browser_session_service.start(
            db,
            self.platform,
            self.search_page_url,
        )

    async def session_state(self, db: Session) -> dict:
        return browser_session_service.state(db, self.platform)

    async def search_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
        mode = settings.boss_search_mode.lower().strip()
        if mode == "fixture":
            return await self._search_fixture_jobs(search, profile)
        if mode != "live":
            raise PlatformDataError(
                f"\u65e0\u6548\u7684 Boss \u641c\u7d22\u6a21\u5f0f\uff1a{settings.boss_search_mode}"
            )

        return await self._search_live_jobs(search, profile)

    async def ensure_search_ready(self) -> None:
        if settings.boss_search_mode.lower().strip() != "live":
            return
        page_url = self._build_page_url({"query": "python"})
        response_bundle = await browser_session_service.fetch_json_with_session(
            self.platform,
            page_url=page_url,
            api_url=settings.boss_search_api_url,
            form_data={"query": "python", "page": "1", "pageSize": "1"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        self._assert_not_blocked(response_bundle, verification_url=page_url)

    async def _search_fixture_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
        wanted_targets = [
            value.lower() for value in search.job_targets or profile.target_roles
        ]
        wanted_cities = set(search.cities or profile.preferred_cities)
        results: list[NormalizedJobDraft] = []

        for raw in self.fixture_jobs:
            haystack = " ".join(
                [
                    raw["title"],
                    raw["company_name"],
                    raw["jd_text"],
                    " ".join(raw.get("tags", [])),
                ]
            ).lower()
            if wanted_targets and not any(
                target.lower() in haystack for target in wanted_targets
            ):
                continue
            if wanted_cities and raw["city"] not in wanted_cities:
                continue

            await asyncio.sleep(random.uniform(0.08, 0.2))
            jd_hash = hashlib.md5(raw["jd_text"].encode("utf-8")).hexdigest()
            results.append(
                NormalizedJobDraft(
                    external_job_id=raw["id"],
                    title=raw["title"],
                    company_name=raw["company_name"],
                    city=raw["city"],
                    salary_text=raw["salary_text"],
                    salary_min=raw["salary_min"],
                    salary_max=raw["salary_max"],
                    experience_text=raw["experience_text"],
                    degree_text=raw["degree_text"],
                    work_mode=raw["work_mode"],
                    url=raw["url"],
                    jd_text=raw["jd_text"],
                    jd_hash=jd_hash,
                    raw_payload=raw,
                )
            )
        return results

    async def _search_live_jobs(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[NormalizedJobDraft]:
        query_terms = self._candidate_queries(search, profile)
        city_targets = self._candidate_cities(search, profile)
        if not query_terms:
            raise PlatformDataError(
                "Boss \u641c\u7d22\u9700\u8981\u81f3\u5c11\u4e00\u4e2a\u5c97\u4f4d\u5173\u952e\u8bcd\u3002"
            )

        results: list[NormalizedJobDraft] = []
        seen_job_ids: set[str] = set()
        combinations = 0

        for query in query_terms:
            for city_name, city_code in city_targets:
                combinations += 1
                if combinations > settings.boss_search_max_queries:
                    break

                cached_jobs = self._load_cached_jobs(query=query, city_code=city_code)
                if cached_jobs is not None:
                    drafts = cached_jobs
                else:
                    await self._throttle_live_search()
                    response_payload = await self._fetch_live_joblist(
                        query=query,
                        city_code=city_code,
                    )
                    drafts = [
                        self._normalize_live_job(
                            item=item,
                            fallback_city=city_name,
                            query=query,
                        )
                        for item in self._extract_job_items(response_payload)
                    ]
                    if drafts:
                        self._save_cached_jobs(
                            query=query,
                            city_code=city_code,
                            drafts=drafts,
                        )

                for draft in drafts:
                    if draft.external_job_id in seen_job_ids:
                        continue
                    seen_job_ids.add(draft.external_job_id)
                    results.append(draft)
            if combinations > settings.boss_search_max_queries:
                break

        if not results:
            raise PlatformDataError(
                "Boss \u76f4\u8058\u672a\u8fd4\u56de\u53ef\u89e3\u6790\u7684\u804c\u4f4d\u7ed3\u679c\u3002"
            )

        return results

    async def _fetch_live_joblist(
        self,
        query: str,
        city_code: str | None,
    ) -> dict[str, Any]:
        page_params: dict[str, str] = {"query": query}
        if city_code:
            page_params["city"] = city_code

        page_url = self._build_page_url(page_params)
        form_data = {
            "query": query,
            "page": "1",
            "pageSize": str(settings.boss_search_page_size),
        }
        if city_code:
            form_data["city"] = city_code

        response_bundle = await browser_session_service.fetch_json_with_session(
            self.platform,
            page_url=page_url,
            api_url=settings.boss_search_api_url,
            form_data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        self._assert_not_blocked(response_bundle, verification_url=page_url)

        page_url_after_nav = str(response_bundle["page_url"])
        response_text = str(response_bundle["response_text"])

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as error:
            raise PlatformBlockedError(
                "Boss \u76f4\u8058\u8fd4\u56de\u4e86\u975e JSON \u9a8c\u8bc1\u9875\u9762\uff0c\u8bf7\u5148\u5728\u4f1a\u8bdd\u6d4f\u89c8\u5668\u4e2d\u5b8c\u6210\u9a8c\u8bc1\u540e\u518d\u91cd\u8bd5\u3002",
                verification_url=page_url_after_nav,
            ) from error
        code = payload.get("code")
        if code in {35, 37}:
            raise PlatformBlockedError(
                payload.get("message")
                or "Boss \u76f4\u8058\u8fd4\u56de\u5b89\u5168\u9a8c\u8bc1\uff0c\u5f53\u524d\u641c\u7d22\u5df2\u88ab\u5e73\u53f0\u963b\u6b62\u3002",
                verification_url=page_url_after_nav,
            )
        if code != 0:
            raise PlatformDataError(
                payload.get("message")
                or f"Boss \u641c\u7d22\u63a5\u53e3\u8fd4\u56de\u5f02\u5e38 code={code}"
            )

        return payload

    @staticmethod
    def _looks_like_verify(url: str, text: str) -> bool:
        lowered_url = str(url).lower()
        lowered_text = text.lower()
        return any(
            marker in lowered_url or marker in lowered_text
            for marker in [
                "/verify.html",
                "security-check",
                "\u5b89\u5168\u9a8c\u8bc1",
                "\u8bf7\u7a0d\u5019",
            ]
        )

    def _assert_not_blocked(
        self,
        response_bundle: dict[str, Any],
        *,
        verification_url: str,
    ) -> None:
        page_url = str(response_bundle.get("page_url", ""))
        page_html = str(response_bundle.get("page_html", ""))
        response_url = str(response_bundle.get("response_url", ""))
        response_text = str(response_bundle.get("response_text", ""))
        if self._looks_like_verify(page_url, page_html) or self._looks_like_verify(
            response_url,
            response_text,
        ):
            raise PlatformBlockedError(
                "Boss \u76f4\u8058\u8981\u6c42\u5b89\u5168\u9a8c\u8bc1\uff0c\u8bf7\u5148\u5728\u6d4f\u89c8\u5668\u91cc\u5b8c\u6210\u9a8c\u8bc1\u540e\u518d\u91cd\u8bd5\u641c\u7d22\u3002",
                verification_url=verification_url,
            )

    def _build_page_url(self, params: dict[str, str]) -> str:
        query_string = urlencode(params)
        return f"{self.search_page_url}?{query_string}" if query_string else self.search_page_url

    @staticmethod
    def _candidate_queries(
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[str]:
        values = search.job_targets or profile.target_roles or profile.must_have_keywords
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidate = value.strip()
            lowered = candidate.lower()
            if not candidate or lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(candidate)
        return normalized

    def _candidate_cities(
        self,
        search: SearchSessionCreate,
        profile: CandidateProfile,
    ) -> list[tuple[str | None, str | None]]:
        values = search.cities or profile.preferred_cities
        if not values:
            return [(None, None)]

        resolved: list[tuple[str | None, str | None]] = []
        seen: set[tuple[str | None, str | None]] = set()
        for city in values:
            normalized_city = self._normalize_city_name(city)
            city_code = self.city_codes.get(normalized_city)
            entry = (normalized_city or None, city_code)
            if entry in seen:
                continue
            seen.add(entry)
            resolved.append(entry)

        return resolved or [(None, None)]

    @staticmethod
    def _normalize_city_name(raw_city: str) -> str:
        candidate = raw_city.strip()
        for separator in ("\u00b7", "-", "_", "/", "\\", " "):
            if separator in candidate:
                candidate = candidate.split(separator, 1)[0].strip()
        if candidate.endswith("\u5e02"):
            candidate = candidate[:-1]
        return candidate

    @staticmethod
    def _extract_job_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        zp_data = payload.get("zpData") or {}
        return (
            zp_data.get("jobList")
            or zp_data.get("list")
            or zp_data.get("jobs")
            or []
        )

    def _normalize_live_job(
        self,
        item: dict[str, Any],
        fallback_city: str | None,
        query: str,
    ) -> NormalizedJobDraft:
        external_job_id = (
            self._first_non_empty(item, "encryptJobId", "jobId", "encryptId")
            or self._job_id_from_url(item.get("jobUrl") or item.get("url") or "")
        )
        if not external_job_id:
            raise PlatformDataError(
                "Boss \u641c\u7d22\u7ed3\u679c\u7f3a\u5c11\u53ef\u7528\u7684\u804c\u4f4d ID\u3002"
            )

        title = self._first_non_empty(item, "jobName", "title", "positionName") or query
        company_name = self._first_non_empty(
            item,
            "brandName",
            "companyName",
            "bossCompanyName",
        ) or "\u672a\u77e5\u516c\u53f8"

        salary_text = self._salary_text(item)
        salary_min, salary_max = self._parse_salary_range(salary_text)
        city = self._display_city(item, fallback_city)
        experience_text = self._first_non_empty(
            item,
            "jobExperience",
            "experienceName",
            "experience",
            "jobExp",
        )
        degree_text = self._first_non_empty(
            item,
            "jobDegree",
            "degreeName",
            "degree",
            "jobDegreeName",
        )
        labels = self._string_values(
            item.get("jobLabels"),
            item.get("skills"),
            item.get("welfareList"),
        )
        summary_text = self._first_non_empty(
            item,
            "postDescription",
            "jobSummary",
            "jobDemand",
            "jobDesc",
            "jobDescription",
            "positionDescription",
        )
        jd_text = " ".join(
            value
            for value in [
                title,
                summary_text,
                " ".join(labels),
                experience_text,
                degree_text,
            ]
            if value
        ).strip()
        if not jd_text:
            jd_text = title

        work_mode = self._infer_work_mode(labels, summary_text)
        url = self._job_detail_url(item, external_job_id)
        jd_hash = hashlib.md5(jd_text.encode("utf-8")).hexdigest()

        raw_payload = dict(item)
        raw_payload["query"] = query
        raw_payload["real_job_detail_url"] = url

        return NormalizedJobDraft(
            external_job_id=external_job_id,
            title=title,
            company_name=company_name,
            city=city or (fallback_city or ""),
            salary_text=salary_text,
            salary_min=salary_min,
            salary_max=salary_max,
            experience_text=experience_text,
            degree_text=degree_text,
            work_mode=work_mode,
            url=url,
            jd_text=jd_text,
            jd_hash=jd_hash,
            raw_payload=raw_payload,
        )

    @staticmethod
    def _first_non_empty(item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _salary_text(self, item: dict[str, Any]) -> str:
        salary = self._first_non_empty(
            item,
            "salaryDesc",
            "jobSalary",
            "salary",
            "salaryStr",
        )
        month = self._first_non_empty(item, "salaryMonthText", "salaryMonth")
        if salary and month and month not in salary:
            return f"{salary}\u00b7{month}"
        return salary or month

    @staticmethod
    def _parse_salary_range(salary_text: str) -> tuple[int, int]:
        matched = re.search(
            r"(?P<low>\d+(?:\.\d+)?)\s*[kK]?\s*[-~]\s*(?P<high>\d+(?:\.\d+)?)\s*[kK]",
            salary_text,
        )
        if not matched:
            return 0, 0
        low = int(float(matched.group("low")) * 1000)
        high = int(float(matched.group("high")) * 1000)
        return low, high

    def _display_city(self, item: dict[str, Any], fallback_city: str | None) -> str:
        city_name = self._first_non_empty(item, "cityName", "city")
        district = self._first_non_empty(
            item,
            "areaDistrict",
            "districtName",
            "businessDistrict",
        )
        if city_name and district:
            return f"{city_name}\u00b7{district}"
        return city_name or fallback_city or ""

    @staticmethod
    def _string_values(*values: Any) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        def append_value(raw: Any) -> None:
            if isinstance(raw, str):
                candidate = raw.strip()
                lowered = candidate.lower()
                if candidate and lowered not in seen:
                    seen.add(lowered)
                    normalized.append(candidate)
                return
            if isinstance(raw, dict):
                for key in ("name", "label", "value", "text"):
                    if isinstance(raw.get(key), str):
                        append_value(raw[key])
                        return
                return
            if isinstance(raw, Iterable):
                for entry in raw:
                    append_value(entry)

        for value in values:
            append_value(value)

        return normalized

    @staticmethod
    def _infer_work_mode(labels: list[str], summary_text: str) -> str:
        haystack = " ".join(labels + [summary_text]).lower()
        if any(
            keyword in haystack
            for keyword in ["\u8fdc\u7a0b", "remote", "\u5c45\u5bb6"]
        ):
            return "remote"
        if any(keyword in haystack for keyword in ["hybrid", "\u6df7\u5408"]):
            return "hybrid"
        if any(
            keyword in haystack
            for keyword in ["onsite", "\u7ebf\u4e0b", "\u5750\u73ed", "\u73b0\u573a"]
        ):
            return "onsite"
        return ""

    def _job_detail_url(self, item: dict[str, Any], external_job_id: str) -> str:
        direct_url = self._first_non_empty(item, "jobUrl", "url")
        if direct_url:
            return urljoin(self.base_url, direct_url)
        return f"{self.base_url}/job_detail/{external_job_id}.html"

    @staticmethod
    def _job_id_from_url(url: str) -> str:
        matched = re.search(r"/job_detail/([^/?#]+)\.html", url)
        return matched.group(1) if matched else ""

    def _cache_path(self, query: str, city_code: str | None) -> Path:
        cache_key = hashlib.sha1(
            f"{query.lower()}::{city_code or 'all'}".encode("utf-8")
        ).hexdigest()
        return self.search_cache_dir / f"{cache_key}.json"

    def _load_cached_jobs(
        self,
        *,
        query: str,
        city_code: str | None,
    ) -> list[NormalizedJobDraft] | None:
        cache_path = self._cache_path(query, city_code)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(payload["created_at"])
            ttl = timedelta(seconds=settings.boss_search_cache_ttl_seconds)
            if datetime.utcnow() - created_at > ttl:
                return None
            return [NormalizedJobDraft(**item) for item in payload.get("jobs", [])]
        except Exception:
            return None

    def _save_cached_jobs(
        self,
        *,
        query: str,
        city_code: str | None,
        drafts: list[NormalizedJobDraft],
    ) -> None:
        cache_path = self._cache_path(query, city_code)
        payload = {
            "created_at": datetime.utcnow().isoformat(),
            "jobs": [draft.__dict__ for draft in drafts],
        }
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _throttle_live_search(self) -> None:
        throttle_path = self.search_cache_dir / "throttle.json"
        now = datetime.utcnow()
        min_interval = settings.boss_search_min_interval_seconds
        if throttle_path.exists():
            try:
                payload = json.loads(throttle_path.read_text(encoding="utf-8"))
                last_request_at = datetime.fromisoformat(payload["last_request_at"])
                wait_seconds = min_interval - (now - last_request_at).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
            except Exception:
                pass

        await asyncio.sleep(random.uniform(0.6, 1.2))
        throttle_path.write_text(
            json.dumps({"last_request_at": datetime.utcnow().isoformat()}),
            encoding="utf-8",
        )

    async def open_review(self, url: str) -> str:
        if not settings.disable_browser_open:
            await browser_session_service.open_runtime_url(self.platform, url)
        return (
            "\u5df2\u5728\u4f1a\u8bdd\u6d4f\u89c8\u5668\u4e2d\u6253\u5f00\u771f\u5b9e"
            "\u804c\u4f4d\u8be6\u60c5\u9875\uff0c\u8bf7\u4f60\u81ea\u884c\u67e5\u770b\u3002"
        )

    async def guided_apply(self, url: str, profile: CandidateProfile) -> str:
        if not settings.disable_browser_open:
            await browser_session_service.open_runtime_url(self.platform, url)
        candidate_name = profile.full_name or "\u5019\u9009\u4eba"
        return (
            f"\u5df2\u4e3a {candidate_name} "
            "\u6253\u5f00\u771f\u5b9e\u804c\u4f4d\u9875\u9762\uff0c\u5e76\u5728\u6700\u7ec8"
            "\u63d0\u4ea4\u524d\u505c\u6b62\u3002"
        )


boss_adapter = BossAdapter()
