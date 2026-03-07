from openresume_api.adapters.base import NormalizedJobDraft
from openresume_api.models import CandidateProfile
from openresume_api.services.matching import matching_service


def test_matching_service_filters_and_scores_expected_roles():
    profile = CandidateProfile(
        id=1,
        target_roles=["前端工程师"],
        preferred_cities=["上海"],
        salary_floor=25000,
        skills=["React", "TypeScript", "Node.js"],
        must_have_keywords=["React", "TypeScript"],
    )
    drafts = [
        NormalizedJobDraft(
            external_job_id="1",
            title="高级前端工程师",
            company_name="A",
            city="上海",
            salary_text="30k-40k",
            salary_min=30000,
            salary_max=40000,
            experience_text="3-5年",
            degree_text="本科",
            work_mode="hybrid",
            url="https://example.com/1",
            jd_text="React TypeScript Node.js 设计系统 工程化",
            jd_hash="hash-1",
            raw_payload={},
        ),
        NormalizedJobDraft(
            external_job_id="2",
            title="后端工程师",
            company_name="B",
            city="北京",
            salary_text="20k-28k",
            salary_min=20000,
            salary_max=28000,
            experience_text="3-5年",
            degree_text="本科",
            work_mode="onsite",
            url="https://example.com/2",
            jd_text="Python FastAPI",
            jd_hash="hash-2",
            raw_payload={},
        ),
    ]

    matches = matching_service.filter_and_score(
        profile=profile,
        drafts=drafts,
        requested_targets=["前端工程师"],
        requested_cities=["上海"],
        requested_keywords=["React", "TypeScript"],
        salary_floor=25000,
    )

    assert len(matches) == 1
    assert matches[0].draft.external_job_id == "1"
    assert matches[0].rule_score > 70
    assert "React" in matches[0].highlights

