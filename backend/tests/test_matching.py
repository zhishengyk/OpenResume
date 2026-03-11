from datetime import datetime

from openresume_api.adapters.base import NormalizedJobDraft
from openresume_api.models import CandidateProfile
from openresume_api.services.matching import matching_service


def make_draft(
    job_id: str,
    *,
    title: str = "Frontend Engineer",
    location_city: str = "Shanghai",
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
        location_raw=location_city,
        location_city=location_city,
        location_country="China",
        remote_type=remote_type,
        description_text=description_text,
        requirements_text=requirements_text,
        apply_url=f"https://jobs.bytedance.com/position/{job_id}/detail",
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
    tech_stack: list[str] | None = None,
    project_experiences: list[dict] | None = None,
    awards: list[dict] | None = None,
    years_experience: int = 5,
) -> CandidateProfile:
    return CandidateProfile(
        id=1,
        target_roles=target_roles or ["Frontend Engineer"],
        preferred_cities=preferred_cities or ["Shanghai"],
        salary_floor=salary_floor,
        skills=skills or ["React", "TypeScript"],
        must_have_keywords=must_have_keywords or [],
        tech_stack=tech_stack or [],
        project_experiences=project_experiences or [],
        awards=awards or [],
        years_experience=years_experience,
    )


def test_matching_service_soft_ranks_mismatches_instead_of_filtering_out():
    profile = make_profile(
        target_roles=["Frontend Engineer"],
        preferred_cities=["Beijing"],
        must_have_keywords=["React", "TypeScript"],
    )
    drafts = [
        make_draft(
            "perfect",
            title="Senior Frontend Engineer",
            location_city="Beijing",
            salary_min=35000,
            description_text="React TypeScript Node.js",
        ),
        make_draft("city_mismatch", location_city="Shanghai", salary_min=35000),
        make_draft("salary_mismatch", location_city="Beijing", salary_min=18000),
        make_draft(
            "target_mismatch",
            title="Backend Engineer",
            location_city="Beijing",
            description_text="Python FastAPI",
        ),
        make_draft(
            "keyword_mismatch",
            location_city="Beijing",
            description_text="Frontend work with Vue",
            requirements_text="JavaScript",
        ),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Beijing"],
        requested_keywords=["React", "TypeScript"],
        salary_floor=30000,
    )

    assert len(matches) == 5
    score_by_id = {item.draft.job_id: item.rule_score for item in matches}
    assert score_by_id["perfect"] > score_by_id["city_mismatch"]
    assert score_by_id["perfect"] > score_by_id["salary_mismatch"]
    assert score_by_id["perfect"] > score_by_id["target_mismatch"]
    assert score_by_id["perfect"] > score_by_id["keyword_mismatch"]


def test_matching_service_marks_soft_mismatch_reasons():
    profile = make_profile(
        target_roles=["Frontend Engineer"],
        preferred_cities=["Beijing"],
        must_have_keywords=["React", "TypeScript"],
    )
    draft = make_draft(
        "mismatch",
        title="Backend Engineer",
        location_city="Shanghai",
        salary_min=20000,
        description_text="Python only",
        requirements_text="Python",
    )

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=[draft],
        requested_targets=["Frontend Engineer"],
        requested_cities=["Beijing"],
        requested_keywords=["React", "TypeScript"],
        salary_floor=30000,
    )

    assert len(matches) == 1
    assert "City preference mismatch" in matches[0].risk_flags
    assert "Salary below floor" in matches[0].risk_flags
    assert "Role keyword match is weak" in matches[0].risk_flags
    assert "Many required keywords missing" in matches[0].risk_flags


def test_matching_service_keeps_campus_and_internship_entries():
    profile = make_profile(target_roles=["Backend Engineer"])
    drafts = [
        make_draft(
            "campus",
            title="校招前端开发工程师",
            employment_type="Campus",
            description_text="React TypeScript",
        ),
        make_draft(
            "intern",
            title="实习前端开发工程师",
            employment_type="Internship",
            description_text="React TypeScript",
        ),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Backend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 2
    for item in matches:
        assert item.draft.job_id in {"campus", "intern"}
        assert "Role keyword match is weak" in item.risk_flags


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


def test_matching_service_adds_existing_risk_flags():
    profile = make_profile(years_experience=2)
    draft = make_draft(
        "1",
        remote_type="onsite",
        description_text="Team leader, 3-5 years experience required",
    )

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=[draft],
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert len(matches) == 1
    risk_flags = set(matches[0].risk_flags)
    assert "Onsite work required" in risk_flags
    assert "May include people management" in risk_flags
    assert "Experience requirement may be high" in risk_flags


def test_matching_service_prefers_portrait_evidence_rich_roles():
    profile = make_profile(
        skills=["React", "TypeScript"],
        tech_stack=["React", "FastAPI", "Redis"],
        project_experiences=[
            {
                "name": "Search Ranking Engine",
                "role": "Lead Engineer",
                "summary": "Built ranking pipeline, caching, and search relevance tuning",
                "technologies": ["React", "FastAPI", "Redis"],
            }
        ],
        awards=[
            {
                "title": "Search Innovation Award",
                "issuer": "Internal Hackathon",
                "year": "2024",
                "summary": "Won for ranking quality improvements",
            }
        ],
    )
    drafts = [
        make_draft(
            "portrait-fit",
            description_text=(
                "React FastAPI Redis role focused on ranking pipeline, search relevance, "
                "and candidate experience improvements"
            ),
            requirements_text="React FastAPI Redis search relevance",
        ),
        make_draft(
            "generic-fit",
            description_text="React TypeScript UI implementation",
            requirements_text="React TypeScript",
        ),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["Frontend Engineer"],
        requested_cities=[],
        requested_keywords=[],
        salary_floor=0,
    )

    assert matches[0].draft.job_id == "portrait-fit"
    assert "FastAPI" in matches[0].highlights
