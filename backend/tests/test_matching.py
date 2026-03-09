from openresume_api.adapters.base import NormalizedJobDraft
from openresume_api.models import CandidateProfile
from openresume_api.services.matching import matching_service


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
            external_job_id="1",
            title="Senior Frontend Engineer",
            company_name="A",
            city="Shanghai",
            salary_text="30k-40k",
            salary_min=30000,
            salary_max=40000,
            experience_text="3-5 years",
            degree_text="Bachelor",
            work_mode="hybrid",
            url="https://example.com/1",
            detail_url="https://example.com/1",
            apply_url="https://example.com/1/apply",
            source_company_url="https://example.com",
            apply_requires_login=True,
            jd_text="React TypeScript Node.js design system engineering",
            jd_hash="hash-1",
            raw_payload={"platform": "official"},
        ),
        NormalizedJobDraft(
            external_job_id="2",
            title="Backend Engineer",
            company_name="B",
            city="Beijing",
            salary_text="20k-28k",
            salary_min=20000,
            salary_max=28000,
            experience_text="3-5 years",
            degree_text="Bachelor",
            work_mode="onsite",
            url="https://example.com/2",
            detail_url="https://example.com/2",
            apply_url="https://example.com/2/apply",
            source_company_url="https://example.com",
            apply_requires_login=True,
            jd_text="Python FastAPI",
            jd_hash="hash-2",
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
    assert matches[0].draft.external_job_id == "1"
    assert matches[0].rule_score > 70
    assert "React" in matches[0].highlights
