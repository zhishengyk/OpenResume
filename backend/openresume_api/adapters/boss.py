from __future__ import annotations

import asyncio
from collections.abc import Iterable
import hashlib
import json
import random
import re
from typing import Any
from urllib.parse import urljoin
import webbrowser

import httpx
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
        "北京": "101010100",
        "上海": "101020100",
        "广州": "101280100",
        "深圳": "101280600",
        "杭州": "101210100",
        "苏州": "101190400",
        "南京": "101190100",
        "成都": "101270100",
        "武汉": "101200100",
        "西安": "101110100",
        "重庆": "101040100",
        "天津": "101030100",
        "长沙": "101250100",
        "郑州": "101180100",
        "合肥": "101220100",
        "厦门": "101230200",
        "福州": "101230100",
        "青岛": "101120200",
        "济南": "101120100",
        "宁波": "101210400",
        "东莞": "101281600",
        "佛山": "101280800",
        "珠海": "101280700",
    }

    def __init__(self) -> None:
        fixtures_path = ROOT_DIR / "openresume_api" / "fixtures" / "boss_jobs.json"
        self.fixture_jobs = json.loads(fixtures_path.read_text(encoding="utf-8"))

    def capability(self) -> PlatformCapabilityResponse:
        return PlatformCapabilityResponse(
            platform=self.platform,
            label="Boss 直聘",
            search_supported=True,
            detail_parse_supported=True,
            review_open_supported=True,
            guided_apply_supported=True,
            rule_pack_version=rule_pack_service.current_version(self.platform),
        )

    async def start_session(self, db: Session) -> None:
        browser_session_service.start(
            db,
            self.platform,
            "https://www.zhipin.com/web/user/",
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
                f"无效的 Boss 搜索模式：{settings.boss_search_mode}"
            )

        return await self._search_live_jobs(search, profile)

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
            raise PlatformDataError("Boss 搜索需要至少一个岗位关键词。")

        client_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Origin": self.base_url,
        }

        results: list[NormalizedJobDraft] = []
        seen_job_ids: set[str] = set()
        combinations = 0

        async with httpx.AsyncClient(
            headers=client_headers,
            follow_redirects=True,
            timeout=20.0,
        ) as client:
            for query in query_terms:
                for city_name, city_code in city_targets:
                    combinations += 1
                    if combinations > settings.boss_search_max_queries:
                        break

                    await asyncio.sleep(random.uniform(0.6, 1.2))
                    response_payload = await self._fetch_live_joblist(
                        client=client,
                        query=query,
                        city_code=city_code,
                    )
                    for item in self._extract_job_items(response_payload):
                        draft = self._normalize_live_job(
                            item=item,
                            fallback_city=city_name,
                            query=query,
                        )
                        if draft.external_job_id in seen_job_ids:
                            continue
                        seen_job_ids.add(draft.external_job_id)
                        results.append(draft)
                if combinations > settings.boss_search_max_queries:
                    break

        if not results:
            raise PlatformDataError("Boss 直聘未返回可解析的职位结果。")

        return results

    async def _fetch_live_joblist(
        self,
        client: httpx.AsyncClient,
        query: str,
        city_code: str | None,
    ) -> dict[str, Any]:
        page_params: dict[str, str] = {"query": query}
        if city_code:
            page_params["city"] = city_code

        page_response = await client.get(
            self.search_page_url,
            params=page_params,
            headers={"Referer": self.base_url},
        )
        page_text = page_response.text
        if self._looks_like_verify(page_response.url, page_text):
            raise PlatformBlockedError(
                "Boss 直聘要求安全验证，请先在浏览器里完成验证后再重试搜索。"
            )

        referer = str(page_response.url)
        form_data = {
            "query": query,
            "page": "1",
            "pageSize": str(settings.boss_search_page_size),
        }
        if city_code:
            form_data["city"] = city_code

        api_response = await client.post(
            settings.boss_search_api_url,
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": referer,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        payload = api_response.json()
        code = payload.get("code")
        if code == 35:
            raise PlatformBlockedError(
                payload.get("message")
                or "Boss 直聘返回安全验证，当前搜索已被平台阻止。"
            )
        if code != 0:
            raise PlatformDataError(
                payload.get("message") or f"Boss 搜索接口返回异常 code={code}"
            )

        return payload

    @staticmethod
    def _looks_like_verify(url: httpx.URL, text: str) -> bool:
        lowered_url = str(url).lower()
        lowered_text = text.lower()
        return any(
            marker in lowered_url or marker in lowered_text
            for marker in [
                "/verify.html",
                "security-check",
                "安全验证",
                "请稍候",
            ]
        )

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
            clean_city = city.strip()
            if not clean_city:
                continue
            city_code = self.city_codes.get(clean_city)
            entry = (clean_city, city_code)
            if entry in seen:
                continue
            seen.add(entry)
            resolved.append(entry)

        return resolved or [(None, None)]

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
            raise PlatformDataError("Boss 搜索结果缺少可用的职位 ID。")

        title = self._first_non_empty(item, "jobName", "title", "positionName") or query
        company_name = self._first_non_empty(
            item,
            "brandName",
            "companyName",
            "bossCompanyName",
        ) or "未知公司"

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
        salary = self._first_non_empty(item, "salaryDesc", "jobSalary", "salary", "salaryStr")
        month = self._first_non_empty(item, "salaryMonthText", "salaryMonth")
        if salary and month and month not in salary:
            return f"{salary}·{month}"
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
        district = self._first_non_empty(item, "areaDistrict", "districtName", "businessDistrict")
        if city_name and district:
            return f"{city_name}·{district}"
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
        if any(keyword in haystack for keyword in ["远程", "remote", "居家"]):
            return "remote"
        if any(keyword in haystack for keyword in ["hybrid", "混合"]):
            return "hybrid"
        if any(keyword in haystack for keyword in ["onsite", "线下", "坐班", "现场"]):
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

    async def open_review(self, url: str) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        return "已在默认浏览器中打开真实职位详情页，请你自行查看。"

    async def guided_apply(self, url: str, profile: CandidateProfile) -> str:
        if not settings.disable_browser_open:
            webbrowser.open(url)
        return (
            f"已为 {profile.full_name or '候选人'} 打开真实职位页面，并在最终提交前停止。"
        )


boss_adapter = BossAdapter()
