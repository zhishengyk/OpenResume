from openresume_api.adapters.boss import BossAdapter


def test_live_job_normalization_builds_real_job_detail_url():
    adapter = BossAdapter()
    draft = adapter._normalize_live_job(
        item={
            "encryptJobId": "3ac31a0a5ff221ba03d-3t-0EVRU",
            "jobName": "高级前端工程师",
            "brandName": "雾屿科技",
            "salaryDesc": "30-45K",
            "salaryMonthText": "15薪",
            "cityName": "上海",
            "areaDistrict": "浦东",
            "jobExperience": "5-8年",
            "jobDegree": "本科",
            "jobLabels": ["React", "TypeScript", "Electron", "混合办公"],
            "postDescription": "负责中后台与桌面应用前端开发。",
        },
        fallback_city="上海",
        query="前端工程师",
    )

    assert draft.external_job_id == "3ac31a0a5ff221ba03d-3t-0EVRU"
    assert (
        draft.url
        == "https://www.zhipin.com/job_detail/3ac31a0a5ff221ba03d-3t-0EVRU.html"
    )
    assert draft.salary_text == "30-45K·15薪"
    assert draft.salary_min == 30000
    assert draft.salary_max == 45000
    assert draft.city == "上海·浦东"
    assert draft.work_mode == "hybrid"
    assert "React" in draft.jd_text
