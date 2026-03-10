from datetime import datetime

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
