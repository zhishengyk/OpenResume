from openresume_api.adapters.official_extractors.base import ExtractedCandidate
from openresume_api.adapters.official_extractors.common import (
    canonicalize_url,
    extract_salary,
    final_dedupe_key,
    hard_filter_reasons,
    merge_candidates,
    normalize_city,
    normalize_title,
)


def make_candidate(
    *,
    title: str = "Senior Frontend Engineer",
    detail_url: str = "https://example.com/jobs/1",
    apply_url: str | None = "https://example.com/jobs/1/apply",
    snippet: str = "React TypeScript frontend platform engineering role",
    city: str = "Remote",
    salary_text: str = "",
    salary_min: int = 0,
    salary_max: int = 0,
    experience_text: str = "",
    degree_text: str = "",
    department: str = "",
    location_text: str = "",
    seen_on: list[str] | None = None,
) -> ExtractedCandidate:
    return ExtractedCandidate(
        title=title,
        detail_url=detail_url,
        apply_url=apply_url,
        snippet=snippet,
        company_url="https://example.com/careers",
        city=city,
        salary_text=salary_text,
        salary_min=salary_min,
        salary_max=salary_max,
        experience_text=experience_text,
        degree_text=degree_text,
        work_mode="hybrid",
        department=department,
        location_text=location_text,
        raw_payload={"seen_on": seen_on or [detail_url]},
    )


def test_normalize_title_removes_noise_tokens():
    value = "\u3010\u6821\u62db\u3011 \u6025\u8058 Senior Frontend Engineer #12345"
    assert normalize_title(value) == "Senior Frontend Engineer"


def test_normalize_city_handles_branch_locations():
    assert normalize_city("Shanghai\u00b7Pudong") == "Shanghai"
    assert normalize_city("\u4e0a\u6d77\u00b7\u6d66\u4e1c") == "\u4e0a\u6d77"
    assert normalize_city("\u5317\u4eac\u5e02") == "\u5317\u4eac"


def test_extract_salary_supports_monthly_and_yearly_formats():
    assert extract_salary("15K-25K") == ("15K-25K", 15000, 25000)
    assert extract_salary("15-25k/\u6708") == ("15-25K/\u6708", 15000, 25000)
    assert extract_salary("30-40\u4e07/\u5e74") == ("30-40\u4e07/\u5e74", 25000, 33333)


def test_canonicalize_url_resolves_and_strips_tracking():
    value = canonicalize_url(
        "/jobs/1/?utm_source=feed&ref=foo&jobId=1#section",
        "https://Example.com/careers/",
    )
    assert value == "https://example.com/jobs/1?jobId=1"


def test_hard_filter_reasons_cover_required_cases():
    assert "missing title" in hard_filter_reasons(
        "",
        "https://example.com/jobs/1",
        "React role",
        ["Frontend Engineer"],
    )
    assert "missing detail url" in hard_filter_reasons(
        "Frontend Engineer",
        "",
        "React role",
        ["Frontend Engineer"],
    )
    assert "noise page" in hard_filter_reasons(
        "FAQ",
        "https://example.com/faq",
        "common questions",
        ["Frontend Engineer"],
    )
    assert "directory page" in hard_filter_reasons(
        "Join Us",
        "https://example.com/jobs",
        "position list",
        ["Frontend Engineer"],
    )
    assert "unrelated role:legal" in hard_filter_reasons(
        "Legal Counsel",
        "https://example.com/jobs/legal",
        "contract review",
        ["Frontend Engineer"],
    )


def test_merge_candidates_prefers_richer_candidate_and_merges_fields():
    primary = make_candidate(
        apply_url="https://example.com/jobs/1/apply",
        snippet="React TypeScript platform work",
        seen_on=["https://example.com/list-a"],
    )
    secondary = make_candidate(
        apply_url=None,
        city="Shanghai",
        salary_text="20K-30K",
        salary_min=20000,
        salary_max=30000,
        degree_text="Bachelor",
        department="Platform",
        location_text="Shanghai",
        snippet="React TypeScript platform engineering role with hiring systems ownership",
        seen_on=["https://example.com/list-b"],
    )

    merged = merge_candidates(primary, secondary)

    assert merged is secondary
    assert merged.apply_url == "https://example.com/jobs/1/apply"
    assert merged.city == "Shanghai"
    assert merged.salary_text == "20K-30K"
    assert merged.department == "Platform"
    assert merged.location_text == "Shanghai"
    assert merged.raw_payload["seen_on"] == [
        "https://example.com/list-b",
        "https://example.com/list-a",
    ]


def test_final_dedupe_key_keeps_city_dimension():
    shanghai = final_dedupe_key(
        "Example Corp",
        "Senior Frontend Engineer",
        "Shanghai",
        "https://example.com/jobs/1",
    )
    hangzhou = final_dedupe_key(
        "Example Corp",
        "Senior Frontend Engineer",
        "Hangzhou",
        "https://example.com/jobs/1",
    )

    assert shanghai != hangzhou
