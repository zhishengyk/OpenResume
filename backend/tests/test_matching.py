from datetime import datetime

from openresume_api.adapters.base import NormalizedJobDraft
from openresume_api.models import CandidateProfile
from openresume_api.services.matching import matching_service


def make_draft(
    job_id: str,
    *,
    title: str = "Frontend Engineer",
    location_city: str = "Shanghai",
    location_raw: str = "",
    salary_min: int | None = 30000,
    salary_max: int | None = 40000,
    description_text: str = "React TypeScript",
    requirements_text: str = "React TypeScript",
    remote_type: str = "hybrid",
    posted_at: datetime | None = None,
    employment_type: str = "Experienced",
) -> NormalizedJobDraft:
    return NormalizedJobDraft(
        source_company="ByteDance",
        source_site="jobs.bytedance.com",
        job_id=job_id,
        title=title,
        employment_type=employment_type,
        location_raw=location_raw or location_city,
        location_city=location_city,
        location_country="China",
        remote_type=remote_type,
        description_text=description_text,
        requirements_text=requirements_text,
        apply_url=f"https://jobs.bytedance.com/experienced/position/{job_id}/detail",
        salary_raw=f"{salary_min}k-{salary_max}k" if salary_min and salary_max else "",
        salary_min=salary_min,
        salary_max=salary_max,
        posted_at=posted_at,
        raw_payload={"platform": "official"},
    )


def make_profile(
    *,
    target_roles: list[str] | None = None,
    preferred_cities: list[str] | None = None,
    salary_floor: int = 0,
    skills: list[str] | None = None,
    must_have_keywords: list[str] | None = None,
    years_experience: int = 5,
) -> CandidateProfile:
    return CandidateProfile(
        id=1,
        target_roles=target_roles or ["Frontend Engineer"],
        preferred_cities=preferred_cities or ["Shanghai"],
        salary_floor=salary_floor,
        skills=skills or ["React", "TypeScript"],
        must_have_keywords=must_have_keywords or [],
        years_experience=years_experience,
    )


def test_matching_service_filters_and_scores_expected_roles():
    profile = CandidateProfile(
        id=1,
        target_roles=["Frontend Engineer"],
        preferred_cities=["Shanghai"],
        salary_floor=25000,
        skills=["React", "TypeScript", "Node.js"],
        must_have_keywords=["React", "TypeScript"],
    )
    drafts = [
        NormalizedJobDraft(
            source_company="ByteDance",
            source_site="jobs.bytedance.com",
            job_id="1",
            title="Senior Frontend Engineer",
            employment_type="Experienced",
            location_raw="Shanghai",
            location_city="Shanghai",
            location_country="China",
            remote_type="hybrid",
            description_text="React TypeScript Node.js design system engineering",
            requirements_text="React TypeScript",
            apply_url="https://jobs.bytedance.com/experienced/position/1/detail",
            salary_raw="30k-40k",
            salary_min=30000,
            salary_max=40000,
            posted_at=datetime(2026, 3, 1),
            raw_payload={"platform": "official"},
        ),
        NormalizedJobDraft(
            source_company="ByteDance",
            source_site="jobs.bytedance.com",
            job_id="2",
            title="Backend Engineer",
            employment_type="Experienced",
            location_raw="Beijing",
            location_city="Beijing",
            location_country="China",
            remote_type="onsite",
            description_text="Python FastAPI",
            requirements_text="Python",
            apply_url="https://jobs.bytedance.com/experienced/position/2/detail",
            salary_raw="20k-28k",
            salary_min=20000,
            salary_max=28000,
            posted_at=datetime(2026, 3, 1),
            raw_payload={"platform": "official"},
        ),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
        requested_keywords=["React", "TypeScript"],
        salary_floor=25000,
    )

    assert len(matches) == 1
    assert matches[0].draft.job_id == "1"
    assert matches[0].rule_score > 70
    assert "React" in matches[0].highlights


def test_matching_service_filters_by_city():
    profile = make_profile(preferred_cities=["Beijing"])
    drafts = [
        make_draft("1", location_city="Shanghai"),
        make_draft("2", location_city="Beijing"),
        make_draft("3", location_city="Shenzhen"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Beijing"],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 1
    assert matches[0].draft.location_city == "Beijing"


def test_matching_service_filters_by_salary_floor():
    profile = make_profile(salary_floor=30000)
    drafts = [
        make_draft("1", salary_min=25000, salary_max=35000),
        make_draft("2", salary_min=35000, salary_max=45000),
        make_draft("3", salary_min=None, salary_max=None),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=30000,
    )

    assert len(matches) == 2
    matched_ids = {m.draft.job_id for m in matches}
    assert "2" in matched_ids
    assert "3" in matched_ids
    assert "1" not in matched_ids


def test_matching_service_filters_by_target_role():
    profile = make_profile(target_roles=["Backend Engineer"])
    drafts = [
        make_draft("1", title="Senior Frontend Engineer"),
        make_draft("2", title="Backend Engineer Python"),
        make_draft("3", title="Full Stack Engineer"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Backend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 1
    assert "Backend" in matches[0].draft.title


def test_matching_service_filters_by_must_have_keywords():
    profile = make_profile(must_have_keywords=["React", "TypeScript"])
    drafts = [
        make_draft("1", description_text="React TypeScript Node.js"),
        make_draft("2", description_text="React only"),
        make_draft("3", description_text="Vue JavaScript"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=["React", "TypeScript"],
        salary_floor=0,
    )

    matched_ids = {m.draft.job_id for m in matches}
    assert "1" in matched_ids
    assert "2" in matched_ids
    assert "3" not in matched_ids


def test_matching_service_returns_empty_for_no_matches():
    profile = make_profile(
        target_roles=["Frontend Engineer"],
        preferred_cities=["Shanghai"],
    )
    drafts = [
        make_draft("1", title="Backend Engineer", location_city="Beijing"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 0


def test_matching_service_handles_empty_drafts():
    profile = make_profile()

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=[],
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 0


def test_matching_service_sorts_by_score_descending():
    profile = make_profile(skills=["React", "TypeScript", "Node.js", "Python", "Go"])
    drafts = [
        make_draft("1", description_text="React TypeScript Node.js Python Go"),
        make_draft("2", description_text="React TypeScript"),
        make_draft("3", description_text="React"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 3
    assert matches[0].rule_score >= matches[1].rule_score
    assert matches[1].rule_score >= matches[2].rule_score


def test_matching_service_detects_onsite_risk_flag():
    profile = make_profile()
    drafts = [
        make_draft("1", remote_type="onsite"),
        make_draft("2", remote_type="hybrid"),
        make_draft("3", remote_type="remote"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    onsite_match = next((m for m in matches if m.draft.job_id == "1"), None)
    assert onsite_match is not None
    assert "需要现场办公" in onsite_match.risk_flags

    hybrid_match = next((m for m in matches if m.draft.job_id == "2"), None)
    assert hybrid_match is not None
    assert "需要现场办公" not in hybrid_match.risk_flags


def test_matching_service_detects_leadership_risk_flag():
    profile = make_profile()
    drafts = [
        make_draft("1", description_text="Team leader position"),
        make_draft("2", description_text="Individual contributor"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    leader_match = next((m for m in matches if m.draft.job_id == "1"), None)
    assert leader_match is not None
    assert "可能包含管理职责" in leader_match.risk_flags


def test_matching_service_detects_experience_risk_flag():
    profile = make_profile(years_experience=2)
    drafts = [
        make_draft("1", description_text="3-5 years experience required"),
        make_draft("2", description_text="Entry level position"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    exp_match = next((m for m in matches if m.draft.job_id == "1"), None)
    assert exp_match is not None
    assert "经验要求可能偏高" in exp_match.risk_flags


def test_matching_service_uses_profile_defaults_when_request_empty():
    profile = make_profile(
        target_roles=["Frontend Engineer"],
        preferred_cities=["Shanghai"],
        skills=["React"],
        must_have_keywords=["React"],
    )
    drafts = [
        make_draft("1", location_city="Shanghai", description_text="React Frontend"),
        make_draft("2", location_city="Beijing", description_text="Vue Backend"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=[],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 1
    assert matches[0].draft.job_id == "1"


def test_matching_service_handles_missing_optional_fields():
    profile = make_profile()
    drafts = [
        make_draft("1", posted_at=None, requirements_text="", salary_min=None),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 1
    assert matches[0].rule_score > 0


def test_matching_service_limits_highlights_to_five():
    profile = make_profile(skills=["React", "TypeScript", "Node.js", "Python", "Go", "Rust", "Java"])
    drafts = [
        make_draft("1", description_text="React TypeScript Node.js Python Go Rust Java"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches[0].highlights) <= 5


def test_matching_service_limits_missing_keywords_to_four():
    profile = make_profile(must_have_keywords=["A", "B", "C", "D", "E", "F"])
    drafts = [
        make_draft("1", description_text="Only A and B mentioned"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=["A", "B", "C", "D", "E", "F"],
        salary_floor=0,
    )

    assert len(matches[0].missing_keywords) <= 4


def test_matching_service_normalizes_city_names():
    profile = make_profile(preferred_cities=["上海"])
    drafts = [
        make_draft("1", location_city="Shanghai"),
        make_draft("2", location_city="北京"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=["上海"],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 1
    assert matches[0].draft.location_city == "Shanghai"


def test_matching_service_case_insensitive_matching():
    profile = make_profile(target_roles=["FRONTEND ENGINEER"])
    drafts = [
        make_draft("1", title="frontend engineer"),
        make_draft("2", title="FRONTEND ENGINEER"),
        make_draft("3", title="Frontend Engineer"),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["FRONTEND ENGINEER"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 3
