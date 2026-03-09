from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
import hashlib
import html
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from .base import DetailExtraction, ExtractedCandidate, FetchPage

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

GENERAL_JOB_HINTS = [
    "engineer",
    "developer",
    "architect",
    "scientist",
    "frontend",
    "front end",
    "backend",
    "back end",
    "full stack",
    "fullstack",
    "devops",
    "sre",
    "ai",
    "ml",
    "algorithm",
    "data",
    "product",
    "designer",
    "qa",
    "test",
    "intern",
    "工程师",
    "开发",
    "前端",
    "后端",
    "全栈",
    "算法",
    "数据",
    "产品",
    "设计",
    "测试",
    "运维",
    "研发",
    "实习",
]

HARD_NOISE_HINTS = [
    "about us",
    "brand",
    "branding",
    "campus guide",
    "contact",
    "event",
    "events",
    "faq",
    "guide",
    "livestream",
    "news",
    "notice",
    "policy",
    "press",
    "宣讲",
    "品牌",
    "校招政策",
    "常见问题",
    "公告",
    "新闻",
    "活动",
    "直播",
    "投递流程",
    "投递说明",
]

DIRECTORY_HINTS = [
    "all jobs",
    "apply guide",
    "career site",
    "campus jobs",
    "category",
    "job category",
    "job list",
    "join us",
    "position list",
    "positions",
    "social jobs",
    "投递指南",
    "加入我们",
    "职位列表",
    "岗位列表",
    "职位类别",
    "岗位类别",
    "全部职位",
    "招聘官网",
]

UNRELATED_ROLE_HINTS = [
    "admin",
    "administration",
    "assistant",
    "customer service",
    "finance",
    "hr",
    "legal",
    "operations",
    "sales",
    "support",
    "财务",
    "法务",
    "行政",
    "客服",
    "销售",
    "运营",
    "人事",
    "采购",
]

TRACKING_QUERY_KEYS = {
    "from",
    "locale",
    "ref",
    "refer",
    "share",
    "source",
    "spm",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

SECTION_MARKERS: dict[str, list[str]] = {
    "responsibilities": [
        "岗位职责",
        "职位描述",
        "工作职责",
        "工作内容",
        "职责描述",
        "you will",
        "responsibilities",
        "what you'll do",
    ],
    "requirements": [
        "任职要求",
        "岗位要求",
        "职位要求",
        "任职资格",
        "资格要求",
        "requirements",
        "qualifications",
        "what you need",
    ],
    "location": [
        "工作地点",
        "base",
        "location",
        "办公地点",
    ],
    "department": [
        "所属部门",
        "部门",
        "department",
        "team",
    ],
}

ROLE_KEYWORD_HINTS: dict[str, list[str]] = {
    "frontend": ["frontend", "front end", "web", "ui", "react", "vue", "前端"],
    "backend": ["backend", "back end", "server", "java", "go", "python", "后端"],
    "full stack": ["full stack", "fullstack", "全栈"],
    "data": ["data", "analytics", "warehouse", "数据"],
    "algorithm": ["algorithm", "ml", "ai", "算法", "机器学习"],
    "product": ["product", "产品"],
    "design": ["design", "designer", "ux", "ui", "设计"],
    "qa": ["qa", "test", "testing", "测试"],
    "devops": ["devops", "sre", "platform", "运维"],
}


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
    "\u5317\u4eac",
    "\u4e0a\u6d77",
    "\u676d\u5dde",
    "\u6df1\u5733",
    "\u5e7f\u5dde",
    "\u82cf\u5dde",
    "\u6210\u90fd",
    "\u5357\u4eac",
    "\u6b66\u6c49",
    "\u897f\u5b89",
]

GENERAL_JOB_HINTS = [
    "engineer",
    "developer",
    "architect",
    "scientist",
    "frontend",
    "front end",
    "backend",
    "back end",
    "full stack",
    "fullstack",
    "devops",
    "sre",
    "ai",
    "ml",
    "algorithm",
    "data",
    "product",
    "designer",
    "qa",
    "test",
    "intern",
    "\u5de5\u7a0b\u5e08",
    "\u5f00\u53d1",
    "\u524d\u7aef",
    "\u540e\u7aef",
    "\u5168\u6808",
    "\u7b97\u6cd5",
    "\u6570\u636e",
    "\u4ea7\u54c1",
    "\u8bbe\u8ba1",
    "\u6d4b\u8bd5",
    "\u8fd0\u7ef4",
    "\u7814\u53d1",
    "\u5b9e\u4e60",
]

HARD_NOISE_HINTS = [
    "about us",
    "brand",
    "branding",
    "campus guide",
    "contact",
    "event",
    "events",
    "faq",
    "guide",
    "livestream",
    "news",
    "notice",
    "policy",
    "press",
    "\u5ba3\u8bb2",
    "\u54c1\u724c",
    "\u6821\u62db\u653f\u7b56",
    "\u5e38\u89c1\u95ee\u9898",
    "\u516c\u544a",
    "\u65b0\u95fb",
    "\u6d3b\u52a8",
    "\u76f4\u64ad",
    "\u6295\u9012\u6d41\u7a0b",
    "\u6295\u9012\u8bf4\u660e",
]

DIRECTORY_HINTS = [
    "all jobs",
    "apply guide",
    "career site",
    "campus jobs",
    "category",
    "job category",
    "job list",
    "join us",
    "position list",
    "positions",
    "social jobs",
    "\u6295\u9012\u6307\u5357",
    "\u52a0\u5165\u6211\u4eec",
    "\u804c\u4f4d\u5217\u8868",
    "\u5c97\u4f4d\u5217\u8868",
    "\u804c\u4f4d\u7c7b\u522b",
    "\u5c97\u4f4d\u7c7b\u522b",
    "\u5168\u90e8\u804c\u4f4d",
    "\u62db\u8058\u5b98\u7f51",
]

UNRELATED_ROLE_HINTS = [
    "admin",
    "administration",
    "assistant",
    "customer service",
    "finance",
    "hr",
    "legal",
    "operations",
    "sales",
    "support",
    "\u8d22\u52a1",
    "\u6cd5\u52a1",
    "\u884c\u653f",
    "\u5ba2\u670d",
    "\u9500\u552e",
    "\u8fd0\u8425",
    "\u4eba\u4e8b",
    "\u91c7\u8d2d",
]

SECTION_MARKERS: dict[str, list[str]] = {
    "responsibilities": [
        "\u5c97\u4f4d\u804c\u8d23",
        "\u804c\u4f4d\u63cf\u8ff0",
        "\u5de5\u4f5c\u804c\u8d23",
        "\u5de5\u4f5c\u5185\u5bb9",
        "\u804c\u8d23\u63cf\u8ff0",
        "you will",
        "responsibilities",
        "what you'll do",
    ],
    "requirements": [
        "\u4efb\u804c\u8981\u6c42",
        "\u5c97\u4f4d\u8981\u6c42",
        "\u804c\u4f4d\u8981\u6c42",
        "\u4efb\u804c\u8d44\u683c",
        "\u8d44\u683c\u8981\u6c42",
        "requirements",
        "qualifications",
        "what you need",
    ],
    "location": [
        "\u5de5\u4f5c\u5730\u70b9",
        "base",
        "location",
        "\u529e\u516c\u5730\u70b9",
    ],
    "department": [
        "\u6240\u5c5e\u90e8\u95e8",
        "\u90e8\u95e8",
        "department",
        "team",
    ],
}

ROLE_KEYWORD_HINTS: dict[str, list[str]] = {
    "frontend": ["frontend", "front end", "web", "ui", "react", "vue", "\u524d\u7aef"],
    "backend": ["backend", "back end", "server", "java", "go", "python", "\u540e\u7aef"],
    "full stack": ["full stack", "fullstack", "\u5168\u6808"],
    "data": ["data", "analytics", "warehouse", "\u6570\u636e"],
    "algorithm": ["algorithm", "ml", "ai", "\u7b97\u6cd5", "\u673a\u5668\u5b66\u4e60"],
    "product": ["product", "\u4ea7\u54c1"],
    "design": ["design", "designer", "ux", "ui", "\u8bbe\u8ba1"],
    "qa": ["qa", "test", "testing", "\u6d4b\u8bd5"],
    "devops": ["devops", "sre", "platform", "\u8fd0\u7ef4"],
}


def strip_html(value: str) -> str:
    cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def normalize_title(value: str) -> str:
    title = strip_html(value)
    title = re.sub(r"(?i)[\[\(【（]\s*(?:校招|社招|急聘|热招)[^\]】）)]*[\]】）)]", " ", title)
    title = re.sub(r"(?i)\b(?:urgent|hot)\b", " ", title)
    title = re.sub(r"(?:急聘|热招|校招|社招)", " ", title)
    title = re.sub(r"(?i)(?:job\s*)?#\s*\d+", " ", title)
    title = re.sub(r"(?i)(?:职位|岗位)?编号[:：#]?\s*\d+", " ", title)
    title = normalize_whitespace(title)
    return title.strip(" -|/")


def normalize_city(value: str) -> str:
    city = normalize_whitespace(value)
    for separator in ("·", "-", "_", "/", "\\", "|", " "):
        if separator in city:
            city = city.split(separator, 1)[0].strip()
    if city.endswith("市"):
        city = city[:-1]
    return city


def canonicalize_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    resolved = urljoin(base_url, html.unescape(url).strip())
    parsed = urlparse(resolved)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    query = urlencode(filtered_query, doseq=True)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            query,
            "",
        )
    )


def extract_city(text: str, requested_cities: list[str]) -> str:
    haystack = normalize_whitespace(text).lower()
    for city in requested_cities:
        normalized = normalize_city(city)
        if normalized and normalized.lower() in haystack:
            return normalized
    for city in COMMON_CITIES:
        normalized = normalize_city(city)
        if normalized and normalized.lower() in haystack:
            return normalized
    return "Remote"


def _convert_salary_number(value: str, multiplier: int) -> int:
    return int(round(float(value) * multiplier))


def extract_salary(text: str) -> tuple[str, int, int]:
    monthly_kk = re.search(
        r"(?i)(\d{1,3}(?:\.\d+)?)\s*(?:[k千])?\s*[-~至]\s*(\d{1,3}(?:\.\d+)?)\s*[k千](?:\s*/\s*(?:月|mo|month))?",
        text,
    )
    if monthly_kk:
        raw = monthly_kk.group(0)
        return (
            normalize_whitespace(raw).upper(),
            _convert_salary_number(monthly_kk.group(1), 1000),
            _convert_salary_number(monthly_kk.group(2), 1000),
        )

    monthly_plain = re.search(
        r"(?i)(\d{4,6})\s*[-~至]\s*(\d{4,6})\s*/?\s*(?:月|mo|month)",
        text,
    )
    if monthly_plain:
        raw = monthly_plain.group(0)
        return (
            normalize_whitespace(raw),
            int(monthly_plain.group(1)),
            int(monthly_plain.group(2)),
        )

    yearly_wan = re.search(
        r"(?i)(\d{1,3}(?:\.\d+)?)\s*[-~至]\s*(\d{1,3}(?:\.\d+)?)\s*万\s*/?\s*年",
        text,
    )
    if yearly_wan:
        raw = yearly_wan.group(0)
        return (
            normalize_whitespace(raw),
            _convert_salary_number(yearly_wan.group(1), 10000) // 12,
            _convert_salary_number(yearly_wan.group(2), 10000) // 12,
        )

    return "", 0, 0


def experience_text(text: str) -> str:
    match = re.search(
        r"(?i)(\d+\s*[-~]\s*\d+\s*(?:years?|yrs?|年)|\d+\+?\s*(?:years?|yrs?|年))",
        text,
    )
    return normalize_whitespace(match.group(1)) if match else ""


def degree_text(text: str) -> str:
    lowered = text.lower()
    if "博士" in text or "phd" in lowered or "doctor" in lowered:
        return "PhD"
    if "硕士" in text or "master" in lowered:
        return "Master"
    if "本科" in text or "bachelor" in lowered:
        return "Bachelor"
    if "大专" in text or "associate" in lowered:
        return "Associate"
    return ""


def work_mode(text: str) -> str:
    lowered = text.lower()
    if "remote" in lowered or "远程" in text:
        return "remote"
    if "hybrid" in lowered or "混合办公" in text or "混合" in text:
        return "hybrid"
    return "onsite"


def stable_external_job_id(
    company_name: str,
    title: str,
    city: str,
    detail_url: str,
) -> str:
    raw = "|".join(
        [
            normalize_whitespace(company_name).lower(),
            normalize_title(title).lower(),
            normalize_city(city).lower(),
            canonicalize_url(detail_url).lower(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def stable_jd_hash(text: str, section_payload: dict[str, Any]) -> str:
    payload = {
        "jd_text": normalize_whitespace(text),
        "sections": section_payload,
    }
    return hashlib.md5(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def target_keywords(requested_targets: list[str]) -> set[str]:
    keywords: set[str] = set()
    for target in requested_targets:
        lowered = normalize_whitespace(target).lower()
        if not lowered:
            continue
        keywords.add(lowered)
        keywords.update(
            token
            for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", lowered)
            if token
        )
        for role, hints in ROLE_KEYWORD_HINTS.items():
            if role in lowered:
                keywords.update(hints)
    return {keyword for keyword in keywords if len(keyword) >= 2}


def matches_requested_targets(text: str, requested_targets: list[str]) -> bool:
    if not requested_targets:
        return True
    lowered = normalize_whitespace(text).lower()
    keywords = target_keywords(requested_targets)
    if not keywords:
        return True
    return any(keyword in lowered for keyword in keywords)


def looks_like_job(title: str, snippet: str, requested_targets: list[str]) -> bool:
    haystack = f"{normalize_title(title)} {normalize_whitespace(snippet)}".lower()
    if any(hint in haystack for hint in HARD_NOISE_HINTS):
        return False
    if requested_targets and matches_requested_targets(haystack, requested_targets):
        return True
    return any(keyword in haystack for keyword in GENERAL_JOB_HINTS)


def is_directory_like(title: str, detail_url: str, snippet: str = "") -> bool:
    haystack = f"{normalize_title(title)} {detail_url} {normalize_whitespace(snippet)}".lower()
    return any(hint in haystack for hint in DIRECTORY_HINTS)


def unrelated_role_reasons(
    title: str,
    snippet: str,
    requested_targets: list[str],
) -> list[str]:
    haystack = f"{normalize_title(title)} {normalize_whitespace(snippet)}".lower()
    if matches_requested_targets(haystack, requested_targets):
        return []
    reasons = [hint for hint in UNRELATED_ROLE_HINTS if hint in haystack]
    if reasons:
        return [f"unrelated role:{reasons[0]}"]
    return []


def hard_filter_reasons(
    title: str,
    detail_url: str,
    snippet: str,
    requested_targets: list[str],
) -> list[str]:
    reasons: list[str] = []
    normalized_title = normalize_title(title)
    if not normalized_title:
        reasons.append("missing title")
    if not canonicalize_url(detail_url):
        reasons.append("missing detail url")
    haystack = f"{normalized_title} {detail_url} {normalize_whitespace(snippet)}".lower()
    if any(hint in haystack for hint in HARD_NOISE_HINTS):
        reasons.append("noise page")
    if is_directory_like(normalized_title, detail_url, snippet):
        reasons.append("directory page")
    reasons.extend(unrelated_role_reasons(normalized_title, snippet, requested_targets))
    return list(dict.fromkeys(reasons))


def classification_from_text(title: str, text: str, detail_url: str) -> str:
    haystack = f"{normalize_title(title)} {detail_url} {normalize_whitespace(text[:2500])}".lower()
    if any(hint in haystack for hint in HARD_NOISE_HINTS):
        return "noise"
    if is_directory_like(title, detail_url, text[:300]):
        return "directory"
    if "position list" in haystack or "job list" in haystack or "职位列表" in haystack or "岗位列表" in haystack:
        return "job_list"
    if has_detail_markers(text) or (len(normalize_whitespace(text)) >= 200 and looks_like_job(title, text[:500], [])):
        return "job_detail"
    if len(normalize_whitespace(text)) >= 120:
        return "job_list"
    return "noise"


def has_detail_markers(text: str) -> bool:
    lowered = normalize_whitespace(text).lower()
    return any(
        marker in lowered
        for marker in [
            "岗位职责",
            "职位描述",
            "工作职责",
            "任职要求",
            "任职资格",
            "职位要求",
            "requirements",
            "responsibilities",
            "qualifications",
        ]
    )


def _section_positions(text: str) -> list[tuple[int, str]]:
    lowered = normalize_whitespace(text).lower()
    positions: list[tuple[int, str]] = []
    for section_name, markers in SECTION_MARKERS.items():
        for marker in markers:
            index = lowered.find(marker.lower())
            if index != -1:
                positions.append((index, section_name))
                break
    return sorted(positions, key=lambda item: item[0])


def extract_detail_sections(text: str) -> dict[str, str]:
    normalized = normalize_whitespace(text)
    sections = {name: "" for name in SECTION_MARKERS}
    positions = _section_positions(normalized)
    for index, section_name in positions:
        later_positions = [value for value, _ in positions if value > index]
        end = later_positions[0] if later_positions else min(len(normalized), index + 1400)
        snippet = normalized[index:end]
        marker = next(
            (
                candidate
                for candidate in SECTION_MARKERS[section_name]
                if candidate.lower() in snippet.lower()
            ),
            "",
        )
        if marker:
            snippet = re.sub(
                rf"(?i)^\s*{re.escape(marker)}[:\uff1a\-\s]*",
                "",
                snippet,
                count=1,
            )
        sections[section_name] = snippet.strip(" -")
    return sections


def _extract_detail_sections_fixed(text: str) -> dict[str, str]:
    normalized = normalize_whitespace(text)
    sections = {name: "" for name in SECTION_MARKERS}
    positions = _section_positions(normalized)
    for index, section_name in positions:
        later_positions = [value for value, _ in positions if value > index]
        end = later_positions[0] if later_positions else min(len(normalized), index + 1400)
        snippet = normalized[index:end]
        marker = next(
            (
                candidate
                for candidate in SECTION_MARKERS[section_name]
                if candidate.lower() in snippet.lower()
            ),
            "",
        )
        if marker:
            snippet = re.sub(
                rf"(?i)^\s*{re.escape(marker)}[:\uff1a\-\s]*",
                "",
                snippet,
                count=1,
            )
        sections[section_name] = snippet.strip(" -")
    return sections


def build_detail_extraction(
    candidate: ExtractedCandidate,
    page: FetchPage,
    requested_targets: list[str],
    requested_cities: list[str],
) -> DetailExtraction:
    text = strip_html(page.text) or candidate.snippet
    sections = _extract_detail_sections_fixed(text)
    classification = classification_from_text(candidate.title, text, page.final_url)
    location_text = sections["location"] or extract_city(text, requested_cities)
    department = sections["department"] or candidate.department
    return DetailExtraction(
        fetched_url=page.final_url,
        html=page.text,
        text=text[:8000],
        classification=classification,
        responsibilities=sections["responsibilities"],
        requirements=sections["requirements"],
        location_text=location_text,
        department=department,
        degree_text=candidate.degree_text or degree_text(text),
        experience_text=candidate.experience_text or experience_text(text),
        apply_url=candidate.apply_url or page.final_url,
        section_payload=sections,
    )


def compute_quality(
    candidate: ExtractedCandidate,
    detail: DetailExtraction,
) -> dict[str, Any]:
    score = 100
    penalty_reasons: list[str] = []
    drop_reasons = list(candidate.raw_payload.get("hard_filter_reasons") or [])
    structured_source = candidate.raw_payload.get("source") in {
        "feishu-json",
        "json-ssr",
        "moka-json",
        "script-json",
    }
    detail_page_found = bool(detail.html)
    detail_is_job_page = detail.classification == "job_detail"
    apply_url_found = bool(candidate.apply_url or detail.apply_url)
    jd_length_ok = len(normalize_whitespace(detail.text)) >= 200

    if not structured_source:
        score -= 8
        penalty_reasons.append("unstructured source")
    if not detail_page_found:
        score -= 15
        penalty_reasons.append("detail fetch failed")
    if detail.classification in {"directory", "noise"}:
        drop_reasons.append(f"detail classified as {detail.classification}")
    elif detail.classification == "job_list":
        score -= 30
        penalty_reasons.append("detail still looks like job list")
    if not detail_is_job_page and detail.classification != "job_list":
        score -= 10
    if not apply_url_found:
        score -= 10
        penalty_reasons.append("missing apply url")
    if not jd_length_ok:
        score -= 20
        penalty_reasons.append("short jd")
    if len(normalize_whitespace(candidate.snippet)) < 30:
        score -= 8
        penalty_reasons.append("short snippet")

    score = max(score, 0)
    if score < 60:
        drop_reasons.append("quality score below threshold")
    tier = "high" if score >= 80 else "medium" if score >= 60 else "low"
    if 60 <= score < 80:
        penalty_reasons.append("quality penalty")

    return {
        "score": score,
        "tier": tier,
        "drop_reasons": list(dict.fromkeys(drop_reasons)),
        "penalty_reasons": list(dict.fromkeys(penalty_reasons)),
        "structured_source": structured_source,
        "detail_page_found": detail_page_found,
        "detail_is_job_page": detail_is_job_page,
        "apply_url_found": apply_url_found,
        "jd_length_ok": jd_length_ok,
    }


def candidate_quality_penalty(candidate: ExtractedCandidate | dict[str, Any]) -> int:
    payload = candidate.raw_payload if isinstance(candidate, ExtractedCandidate) else candidate
    quality = (payload or {}).get("quality") or {}
    score = int(quality.get("score") or 0)
    return 12 if 60 <= score < 80 else 0


def candidate_detail_key(candidate: ExtractedCandidate) -> str:
    return canonicalize_url(candidate.detail_url, candidate.company_url)


def final_dedupe_key(
    company_name: str,
    title: str,
    city: str,
    detail_url: str,
) -> tuple[str, str, str, str]:
    return (
        normalize_whitespace(company_name).lower(),
        normalize_title(title).lower(),
        normalize_city(city).lower(),
        canonicalize_url(detail_url).lower(),
    )


def candidate_richness(candidate: ExtractedCandidate) -> int:
    return sum(
        [
            15 if candidate.apply_url else 0,
            12 if candidate.salary_text else 0,
            8 if candidate.city and candidate.city != "Remote" else 0,
            6 if candidate.experience_text else 0,
            6 if candidate.degree_text else 0,
            min(len(normalize_whitespace(candidate.snippet)), 300) // 10,
        ]
    )


def merge_candidates(
    primary: ExtractedCandidate,
    secondary: ExtractedCandidate,
) -> ExtractedCandidate:
    base = primary if candidate_richness(primary) >= candidate_richness(secondary) else secondary
    other = secondary if base is primary else primary
    seen_on = [
        *list(base.raw_payload.get("seen_on") or []),
        *list(other.raw_payload.get("seen_on") or []),
    ]
    base.raw_payload["seen_on"] = list(dict.fromkeys(seen_on))
    if not base.apply_url:
        base.apply_url = other.apply_url
    if not base.salary_text and other.salary_text:
        base.salary_text = other.salary_text
        base.salary_min = other.salary_min
        base.salary_max = other.salary_max
    if base.city == "Remote" and other.city != "Remote":
        base.city = other.city
    if not base.snippet and other.snippet:
        base.snippet = other.snippet
    if not base.department and other.department:
        base.department = other.department
    if not base.location_text and other.location_text:
        base.location_text = other.location_text
    return base


def find_script_blocks(html_text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for match in re.finditer(r"(?is)<script([^>]*)>(.*?)</script>", html_text):
        attrs = match.group(1) or ""
        block: dict[str, str] = {
            "attrs": attrs,
            "content": (match.group(2) or "").strip(),
        }
        id_match = re.search(r'id=["\']([^"\']+)["\']', attrs, re.I)
        type_match = re.search(r'type=["\']([^"\']+)["\']', attrs, re.I)
        src_match = re.search(r'src=["\']([^"\']+)["\']', attrs, re.I)
        if id_match:
            block["id"] = id_match.group(1)
        if type_match:
            block["type"] = type_match.group(1)
        if src_match:
            block["src"] = src_match.group(1)
        blocks.append(block)
    return blocks


def find_anchor_blocks(html_text: str) -> list[tuple[str, str]]:
    return re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_text)


def _first_string(payload: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _first_nested_string(payload: dict[str, Any], keys: Iterable[str]) -> str:
    value = _first_string(payload, keys)
    if value:
        return value
    for key in keys:
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_value = _first_string(nested, ["zh_cn", "i18n", "name", "title", "value"])
            if nested_value:
                return nested_value
    return ""


def _stringify_description(value: Any) -> str:
    if isinstance(value, str):
        return strip_html(value)
    if isinstance(value, list):
        return normalize_whitespace(" ".join(_stringify_description(item) for item in value))
    if isinstance(value, dict):
        return normalize_whitespace(
            " ".join(_stringify_description(item) for item in value.values())
        )
    return ""


def walk_json_jobs(
    payload: Any,
    company_url: str,
    requested_cities: list[str],
    source_name: str,
) -> list[ExtractedCandidate]:
    candidates: list[ExtractedCandidate] = []
    if isinstance(payload, dict):
        title = _first_nested_string(
            payload,
            [
                "title",
                "name",
                "jobName",
                "job_name",
                "positionName",
                "position_name",
                "postName",
            ],
        )
        description = _stringify_description(
            payload.get("description")
            or payload.get("jd")
            or payload.get("detail")
            or payload.get("content")
            or payload.get("jobDescription")
            or payload.get("summary")
        )
        url = _first_string(
            payload,
            [
                "url",
                "link",
                "jobUrl",
                "detailUrl",
                "applyUrl",
                "website_path",
            ],
        )
        if title and url:
            detail_url = canonicalize_url(url, company_url)
            snippet = description or normalize_title(title)
            if detail_url:
                salary_text, salary_min, salary_max = extract_salary(snippet)
                city_text = _first_nested_string(
                    payload,
                    ["city", "location", "address", "jobCity", "city_name", "location_name"],
                )
                department = _first_nested_string(
                    payload,
                    ["department", "dept", "function", "jobCategory", "category", "zhineng"],
                )
                candidates.append(
                    ExtractedCandidate(
                        title=normalize_title(title),
                        detail_url=detail_url,
                        apply_url=detail_url,
                        snippet=snippet[:3000],
                        company_url=company_url,
                        city=extract_city(city_text or snippet, requested_cities),
                        salary_text=salary_text,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        experience_text=experience_text(snippet),
                        degree_text=degree_text(snippet),
                        work_mode=work_mode(snippet),
                        department=department,
                        location_text=city_text,
                        raw_payload={
                            "source": source_name,
                            "payload": payload,
                            "seen_on": [detail_url],
                        },
                    )
                )
        for value in payload.values():
            candidates.extend(walk_json_jobs(value, company_url, requested_cities, source_name))
    elif isinstance(payload, list):
        for item in payload:
            candidates.extend(walk_json_jobs(item, company_url, requested_cities, source_name))
    return candidates


def raw_payload_snapshot(candidate: ExtractedCandidate, detail: DetailExtraction) -> dict[str, Any]:
    return {
        **candidate.raw_payload,
        "detail_sections": detail.section_payload,
        "detail_classification": detail.classification,
        "detail_fetch_url": detail.fetched_url,
        "department": detail.department or candidate.department,
        "location_text": detail.location_text or candidate.location_text,
    }


def detail_sections_blob(detail: DetailExtraction) -> dict[str, Any]:
    payload = {
        "responsibilities": detail.responsibilities,
        "requirements": detail.requirements,
        "location_text": detail.location_text,
        "department": detail.department,
        "degree_text": detail.degree_text,
        "experience_text": detail.experience_text,
    }
    return {key: value for key, value in payload.items() if value}


def fetch_page_to_dict(page: FetchPage) -> dict[str, Any]:
    return asdict(page)


def normalize_title(value: str) -> str:
    title = strip_html(value)
    title = re.sub(
        r"(?i)[\[\(\u3010\uff08]\s*(?:campus|social|urgent|hot|\u6821\u62db|\u793e\u62db|\u6025\u8058|\u70ed\u62db)[^\]\)\u3011\uff09]*[\]\)\u3011\uff09]",
        " ",
        title,
    )
    title = re.sub(r"(?i)\b(?:urgent|hot|campus|social)\b", " ", title)
    title = re.sub(r"(?:\u6025\u8058|\u70ed\u62db|\u6821\u62db|\u793e\u62db)", " ", title)
    title = re.sub(r"(?i)(?:job\s*)?#\s*\d+", " ", title)
    title = re.sub(
        r"(?i)(?:job\s*)?(?:id|code|req(?:uisition)?(?:\s*id)?)[:#]?\s*\d+",
        " ",
        title,
    )
    title = re.sub(
        r"(?:\u804c\u4f4d|\u5c97\u4f4d)?(?:\u7f16\u53f7|id)[:\uff1a#]?\s*\d+",
        " ",
        title,
    )
    title = normalize_whitespace(title)
    return title.strip(" -|/")


def normalize_city(value: str) -> str:
    city = normalize_whitespace(value)
    city = re.split(r"\s*[·・•/_|,，(（]\s*|\s+-\s+", city, maxsplit=1)[0].strip()
    if city.endswith("\u5e02"):
        city = city[:-1]
    return city


def extract_salary(text: str) -> tuple[str, int, int]:
    normalized = normalize_whitespace(text)
    monthly_kk = re.search(
        r"(?i)(\d{1,3}(?:\.\d+)?)\s*k?\s*[-~\u81f3\u5230]\s*(\d{1,3}(?:\.\d+)?)\s*k(?:\s*/\s*(?:\u6708|mo|month))?",
        normalized,
    )
    if monthly_kk:
        raw = monthly_kk.group(0)
        return (
            normalize_whitespace(raw).upper(),
            _convert_salary_number(monthly_kk.group(1), 1000),
            _convert_salary_number(monthly_kk.group(2), 1000),
        )

    monthly_plain = re.search(
        r"(?i)(\d{4,6})\s*[-~\u81f3\u5230]\s*(\d{4,6})\s*/?\s*(?:\u6708|mo|month)",
        normalized,
    )
    if monthly_plain:
        raw = monthly_plain.group(0)
        return (
            normalize_whitespace(raw),
            int(monthly_plain.group(1)),
            int(monthly_plain.group(2)),
        )

    yearly_wan = re.search(
        r"(?i)(\d{1,3}(?:\.\d+)?)\s*[-~\u81f3\u5230]\s*(\d{1,3}(?:\.\d+)?)\s*(?:\u4e07|wan)\s*/?\s*(?:\u5e74|yr|year)",
        normalized,
    )
    if yearly_wan:
        raw = yearly_wan.group(0)
        return (
            normalize_whitespace(raw),
            _convert_salary_number(yearly_wan.group(1), 10000) // 12,
            _convert_salary_number(yearly_wan.group(2), 10000) // 12,
        )

    return "", 0, 0


def experience_text(text: str) -> str:
    match = re.search(
        r"(?i)(\d+\s*[-~]\s*\d+\s*(?:years?|yrs?|\u5e74)|\d+\+?\s*(?:years?|yrs?|\u5e74))",
        text,
    )
    return normalize_whitespace(match.group(1)) if match else ""


def degree_text(text: str) -> str:
    lowered = text.lower()
    if "\u535a\u58eb" in text or "phd" in lowered or "doctor" in lowered:
        return "PhD"
    if "\u7855\u58eb" in text or "master" in lowered:
        return "Master"
    if "\u672c\u79d1" in text or "bachelor" in lowered:
        return "Bachelor"
    if "\u5927\u4e13" in text or "associate" in lowered:
        return "Associate"
    return ""


def work_mode(text: str) -> str:
    lowered = text.lower()
    if "remote" in lowered or "\u8fdc\u7a0b" in text:
        return "remote"
    if "hybrid" in lowered or "\u6df7\u5408\u529e\u516c" in text or "\u6df7\u5408" in text:
        return "hybrid"
    return "onsite"


def classification_from_text(title: str, text: str, detail_url: str) -> str:
    haystack = f"{normalize_title(title)} {detail_url} {normalize_whitespace(text[:2500])}".lower()
    if any(hint in haystack for hint in HARD_NOISE_HINTS):
        return "noise"
    if is_directory_like(title, detail_url, text[:300]):
        return "directory"
    if (
        "position list" in haystack
        or "job list" in haystack
        or "\u804c\u4f4d\u5217\u8868" in haystack
        or "\u5c97\u4f4d\u5217\u8868" in haystack
    ):
        return "job_list"
    if has_detail_markers(text) or (
        len(normalize_whitespace(text)) >= 200 and looks_like_job(title, text[:500], [])
    ):
        return "job_detail"
    if len(normalize_whitespace(text)) >= 120:
        return "job_list"
    return "noise"


def has_detail_markers(text: str) -> bool:
    lowered = normalize_whitespace(text).lower()
    return any(
        marker in lowered
        for marker in [
            "\u5c97\u4f4d\u804c\u8d23",
            "\u804c\u4f4d\u63cf\u8ff0",
            "\u5de5\u4f5c\u804c\u8d23",
            "\u4efb\u804c\u8981\u6c42",
            "\u4efb\u804c\u8d44\u683c",
            "\u804c\u4f4d\u8981\u6c42",
            "requirements",
            "responsibilities",
            "qualifications",
        ]
    )
