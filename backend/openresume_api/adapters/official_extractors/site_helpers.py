from __future__ import annotations

from collections.abc import Iterable, Sequence
import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

from .base import DetailExtraction, ExtractedCandidate, FetchPage
from .common import (
    canonicalize_url,
    classification_from_text,
    degree_text,
    experience_text,
    extract_city,
    extract_salary,
    find_anchor_blocks,
    find_script_blocks,
    normalize_title,
    normalize_whitespace,
    work_mode,
)

PAGE_BUNDLE_CONTENT_TYPE = "application/vnd.openresume.page-bundle+json"

JSON_SCRIPT_IDS = {
    "__next_data__",
    "__nuxt__",
    "js-websiteinfo",
    "js-websiteinfo",
}


def response_to_page(requested_url: str, response: httpx.Response) -> FetchPage:
    return FetchPage(
        requested_url=requested_url,
        final_url=str(response.url),
        text=response.text,
        status_code=response.status_code,
        content_type=response.headers.get("content-type", ""),
    )


async def safe_fetch_page(client: httpx.AsyncClient, url: str) -> FetchPage | None:
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
    except Exception:
        return None
    return response_to_page(url, response)


def bundle_pages(
    root_page: FetchPage,
    pages: Iterable[FetchPage],
    metadata: dict[str, Any] | None = None,
) -> FetchPage:
    unique_pages: list[FetchPage] = []
    seen: set[tuple[str, str]] = set()
    for page in [root_page, *list(pages)]:
        key = (
            canonicalize_url(page.requested_url or page.final_url),
            canonicalize_url(page.final_url or page.requested_url),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_pages.append(page)
    return FetchPage(
        requested_url=root_page.requested_url,
        final_url=root_page.final_url,
        text=json.dumps(
            {
                "pages": [
                    {
                        "requested_url": page.requested_url,
                        "final_url": page.final_url,
                        "text": page.text,
                        "status_code": page.status_code,
                        "content_type": page.content_type,
                    }
                    for page in unique_pages
                ],
                "metadata": metadata or {},
            },
            ensure_ascii=False,
        ),
        status_code=root_page.status_code,
        content_type=PAGE_BUNDLE_CONTENT_TYPE,
    )


def unbundle_pages(page: FetchPage) -> tuple[list[FetchPage], dict[str, Any]]:
    if page.content_type != PAGE_BUNDLE_CONTENT_TYPE:
        return [page], {}
    try:
        payload = json.loads(page.text)
    except Exception:
        return [page], {}
    bundled_pages: list[FetchPage] = []
    for item in payload.get("pages") or []:
        if not isinstance(item, dict):
            continue
        bundled_pages.append(
            FetchPage(
                requested_url=str(item.get("requested_url") or ""),
                final_url=str(item.get("final_url") or item.get("requested_url") or ""),
                text=str(item.get("text") or ""),
                status_code=int(item.get("status_code") or 0),
                content_type=str(item.get("content_type") or ""),
            )
        )
    return bundled_pages or [page], payload.get("metadata") or {}


def first_string(payload: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def first_nested_string(payload: dict[str, Any], keys: Iterable[str]) -> str:
    direct = first_string(payload, keys)
    if direct:
        return direct
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            nested = first_string(value, ["zh_cn", "zhCN", "title", "name", "label", "value"])
            if nested:
                return nested
    return ""


def stringify_value(value: Any) -> str:
    if isinstance(value, str):
        return normalize_whitespace(value)
    if isinstance(value, dict):
        return normalize_whitespace(" ".join(stringify_value(item) for item in value.values()))
    if isinstance(value, list):
        return normalize_whitespace(" ".join(stringify_value(item) for item in value))
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def payload_dicts(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            yield from payload_dicts(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from payload_dicts(item)


def matching_payloads(payloads: Sequence[object], needles: Sequence[str]) -> list[dict[str, Any]]:
    normalized_needles = [needle.lower() for needle in needles if needle]
    if not normalized_needles:
        return []
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        for item in payload_dicts(payload):
            blob = json.dumps(item, ensure_ascii=False, sort_keys=True)
            lowered = blob.lower()
            if not any(needle in lowered for needle in normalized_needles):
                continue
            if blob in seen:
                continue
            seen.add(blob)
            matches.append(item)
    return matches


def build_candidate_from_payload(
    *,
    title: str,
    detail_url: str,
    company_url: str,
    requested_cities: list[str],
    source_name: str,
    payload: dict[str, Any],
    description: str = "",
    city_text: str = "",
    department: str = "",
    apply_url: str | None = None,
) -> ExtractedCandidate | None:
    normalized_title = normalize_title(title)
    normalized_detail_url = canonicalize_url(detail_url, company_url)
    if not normalized_title or not normalized_detail_url:
        return None
    snippet = normalize_whitespace(description) or normalized_title
    salary_text, salary_min, salary_max = extract_salary(snippet)
    return ExtractedCandidate(
        title=normalized_title,
        detail_url=normalized_detail_url,
        apply_url=canonicalize_url(apply_url or normalized_detail_url, company_url),
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
            "seen_on": [normalized_detail_url],
        },
    )


def json_payloads_from_page(page: FetchPage) -> list[object]:
    payloads: list[object] = []
    if "json" in page.content_type.lower() or page.final_url.lower().endswith(".json"):
        try:
            payloads.append(json.loads(page.text))
        except Exception:
            pass

    decoded_page = html.unescape(page.text)
    for block in find_script_blocks(page.text):
        raw = html.unescape((block.get("content") or "").strip())
        if not raw:
            continue
        block_type = (block.get("type") or "").lower()
        block_id = (block.get("id") or "").lower()
        if (
            "json" not in block_type
            and block_id not in JSON_SCRIPT_IDS
            and "__initial_state__" not in raw.lower()
            and "__next_data__" not in raw.lower()
            and "__nuxt__" not in raw.lower()
            and "__preloaded_state__" not in raw.lower()
        ):
            continue
        for candidate in _json_candidates_from_text(raw):
            try:
                payloads.append(json.loads(candidate))
            except Exception:
                continue

    for candidate in _json_candidates_from_text(decoded_page):
        try:
            payloads.append(json.loads(candidate))
        except Exception:
            continue
    return payloads


def _json_candidates_from_text(text: str) -> list[str]:
    candidates = [text.strip().rstrip(";")]
    patterns = [
        re.compile(r"(?is)(?:window\.)?__NEXT_DATA__\s*=\s*(\{.*?\})\s*;"),
        re.compile(r"(?is)(?:window\.)?__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;"),
        re.compile(r"(?is)(?:window\.)?__NUXT__\s*=\s*(\{.*?\})\s*;"),
        re.compile(r"(?is)(?:window\.)?__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;"),
    ]
    for pattern in patterns:
        candidates.extend(match.group(1).strip() for match in pattern.finditer(text))
    cleaned: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = re.sub(r"^\s*window\.[A-Z0-9_]+\s*=\s*", "", candidate, flags=re.I)
        value = value.strip().rstrip(";")
        if not value or value in seen:
            continue
        if value[0] not in "[{":
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def next_data_url(page: FetchPage) -> str:
    parsed = urlparse(page.final_url)
    path = parsed.path or "/"
    if path.endswith("/") and path != "/":
        path = path[:-1]
    if path == "/":
        path = "/index"
    build_id = ""
    for payload in json_payloads_from_page(page):
        if isinstance(payload, dict) and isinstance(payload.get("buildId"), str):
            build_id = payload["buildId"]
            break
    if not build_id:
        return ""
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            f"/_next/data/{build_id}{path}.json",
            "",
            parsed.query,
            "",
        )
    )


def script_src_urls(
    page: FetchPage,
    *,
    allowed_hosts: set[str] | None = None,
    limit: int = 12,
) -> list[str]:
    urls: list[str] = []
    for block in find_script_blocks(page.text):
        src = block.get("src") or ""
        normalized = canonicalize_url(src, page.final_url)
        if not normalized:
            continue
        host = urlparse(normalized).netloc.lower()
        if allowed_hosts and host not in allowed_hosts:
            continue
        urls.append(normalized)
        if len(urls) >= limit:
            break
    return list(dict.fromkeys(urls))


def anchor_urls(
    page: FetchPage,
    *,
    allowed_hosts: set[str] | None = None,
    include_keywords: Sequence[str] = (),
    limit: int = 24,
) -> list[str]:
    urls: list[str] = []
    lowered_keywords = [keyword.lower() for keyword in include_keywords]
    for href, label in find_anchor_blocks(page.text):
        normalized = canonicalize_url(href, page.final_url)
        if not normalized:
            continue
        host = urlparse(normalized).netloc.lower()
        if allowed_hosts and host not in allowed_hosts:
            continue
        haystack = f"{normalized} {label}".lower()
        if lowered_keywords and not any(keyword in haystack for keyword in lowered_keywords):
            continue
        urls.append(normalized)
        if len(urls) >= limit:
            break
    return list(dict.fromkeys(urls))


def text_urls(
    text: str,
    *,
    base_url: str,
    allowed_hosts: set[str] | None = None,
    include_keywords: Sequence[str] = (),
    limit: int = 32,
) -> list[str]:
    urls: list[str] = []
    lowered_keywords = [keyword.lower() for keyword in include_keywords]
    patterns = [
        re.compile(r"https?://[^\s\"'<>]+", re.I),
        re.compile(r"(?:(?<=\")|(?<=\')|(?<=\b))(\/[A-Za-z0-9_\-?&=./%]+)", re.I),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group(0)
            normalized = canonicalize_url(value, base_url)
            if not normalized:
                continue
            host = urlparse(normalized).netloc.lower()
            if allowed_hosts and host not in allowed_hosts:
                continue
            haystack = normalized.lower()
            if lowered_keywords and not any(keyword in haystack for keyword in lowered_keywords):
                continue
            urls.append(normalized)
            if len(urls) >= limit:
                return list(dict.fromkeys(urls))
    return list(dict.fromkeys(urls))


def page_query_value(url: str, key: str) -> str:
    return (parse_qs(urlparse(url).query).get(key) or [""])[0]


def payload_detail_extraction(
    *,
    candidate: ExtractedCandidate,
    page: FetchPage,
    payload: dict[str, Any],
    requested_cities: list[str],
    responsibilities_keys: Sequence[str],
    requirements_keys: Sequence[str],
    description_keys: Sequence[str] = (),
    location_keys: Sequence[str] = (),
    department_keys: Sequence[str] = (),
    title_keys: Sequence[str] = (),
) -> DetailExtraction | None:
    responsibilities = stringify_value(
        next(
            (payload.get(key) for key in responsibilities_keys if payload.get(key) is not None),
            "",
        )
    )
    requirements = stringify_value(
        next(
            (payload.get(key) for key in requirements_keys if payload.get(key) is not None),
            "",
        )
    )
    description = stringify_value(
        next((payload.get(key) for key in description_keys if payload.get(key) is not None), "")
    )
    title = first_nested_string(payload, title_keys) or candidate.title
    location_text = first_nested_string(payload, location_keys) or candidate.location_text
    department = first_nested_string(payload, department_keys) or candidate.department
    text = normalize_whitespace(
        " ".join(
            part
            for part in [
                title,
                responsibilities,
                requirements,
                description,
                location_text,
                department,
            ]
            if part
        )
    )
    if len(text) < 80:
        return None
    return DetailExtraction(
        fetched_url=page.final_url or candidate.detail_url,
        html=page.text,
        text=text[:8000],
        classification=classification_from_text(candidate.title, text, candidate.detail_url),
        responsibilities=responsibilities,
        requirements=requirements,
        location_text=location_text or extract_city(text, requested_cities),
        department=department,
        degree_text=candidate.degree_text or degree_text(text),
        experience_text=candidate.experience_text or experience_text(text),
        apply_url=candidate.apply_url or candidate.detail_url,
        section_payload={
            key: value
            for key, value in {
                "responsibilities": responsibilities,
                "requirements": requirements,
                "location": location_text,
                "department": department,
            }.items()
            if value
        },
    )
