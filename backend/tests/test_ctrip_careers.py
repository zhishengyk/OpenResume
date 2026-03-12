import json

import httpx

from openresume_api.career_collectors.providers.ctrip_careers import (
    CtripCareerClient,
    VARIANT_CONFIGS,
)


def build_client(handler, *, max_pages: int = 3, page_size: int = 20):
    transport = httpx.MockTransport(handler)
    return CtripCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_categories():
    assert VARIANT_CONFIGS["experienced"].category == 1
    assert VARIANT_CONFIGS["campus"].category == 2
    assert VARIANT_CONFIGS["internship"].category == 2


def test_collect_jobs_filters_campus_and_internship_by_kind_name():
    observed_categories: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/hrrecruit/getJobAd":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        body = json.loads(request.content.decode("utf-8"))
        condition = body.get("condition") or {}
        if "fromId" in condition:
            return httpx.Response(
                200,
                json={
                    "retCode": "201",
                    "retValue": {"recruitJobAdList": [{"fromId": "MJ1", "jobTitle": "detail"}]},
                },
            )

        observed_categories.append(int(condition.get("category") or 0))
        return httpx.Response(
            200,
            json={
                "retCode": "201",
                "retValue": {
                    "total": 2,
                    "recruitJobAdList": [
                        {"fromId": "MJ1", "jobTitle": "Graduate Role", "kindName": "Fresh Graduates", "publishDate": "2026-03-11"},
                        {"fromId": "MJ2", "jobTitle": "Summer Role", "kindName": "Summer Intern", "publishDate": "2026-03-10"},
                    ],
                },
            },
        )

    client = build_client(handler, max_pages=1, page_size=20)
    campus_jobs = client.collect_jobs(variant="campus", keywords=["data"])
    internship_jobs = client.collect_jobs(variant="internship", keywords=["data"])

    assert [item["fromId"] for item in campus_jobs] == ["MJ1"]
    assert [item["fromId"] for item in internship_jobs] == ["MJ2"]
    assert observed_categories == [2, 2]


def test_get_job_detail_returns_first_record():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/hrrecruit/getJobAd":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        body = json.loads(request.content.decode("utf-8"))
        condition = body.get("condition") or {}
        assert condition.get("fromId") == ["MJ033774"]
        return httpx.Response(
            200,
            json={
                "retCode": "201",
                "retValue": {
                    "recruitJobAdList": [
                        {"fromId": "MJ033774", "jobTitle": "Role A", "requirements": "<p>desc</p>"}
                    ]
                },
            },
        )

    client = build_client(handler)
    detail = client.get_job_detail(job_id="MJ033774")
    assert detail["fromId"] == "MJ033774"
    assert detail["jobTitle"] == "Role A"


def test_detail_url_uses_expected_route():
    client = CtripCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert client.detail_url(variant="experienced", job_id="job-1").endswith("/experienced/job-detail/job-1")
    assert client.detail_url(variant="campus", job_id="job-2").endswith("/campus/job-detail/job-2")
