import json

import httpx

from openresume_api.career_collectors.providers.meituan_official import (
    MeituanOfficialClient,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return MeituanOfficialClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_collect_jobs_dedupes_across_keywords():
    seen_keywords: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/official/job/getJobList":
            payload = json.loads(request.content.decode("utf-8"))
            seen_keywords.append(payload.get("keywords"))
            keyword = payload.get("keywords", "")
            if keyword == "frontend":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "list": [{"jobUnionId": "1", "name": "Frontend A", "refreshTime": 1000}],
                            "page": {"totalPage": 1},
                        },
                        "status": 1,
                    },
                )
            if keyword == "react":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "list": [
                                {"jobUnionId": "1", "name": "Frontend A", "refreshTime": 1000},
                                {"jobUnionId": "2", "name": "Frontend B", "refreshTime": 2000},
                            ],
                            "page": {"totalPage": 1},
                        },
                        "status": 1,
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend", "react"])
    assert [job["jobUnionId"] for job in jobs] == ["2", "1"]
    assert seen_keywords == ["frontend", "react"]


def test_collect_jobs_falls_back_to_empty_keyword():
    seen_keywords: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/official/job/getJobList":
            payload = json.loads(request.content.decode("utf-8"))
            seen_keywords.append(payload.get("keywords"))
            if payload.get("keywords") == "frontend":
                return httpx.Response(
                    200,
                    json={"data": {"list": [], "page": {"totalPage": 0}}, "status": 1},
                )
            if "keywords" not in payload:
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "list": [{"jobUnionId": "9", "name": "Fallback", "refreshTime": 3000}],
                            "page": {"totalPage": 1},
                        },
                        "status": 1,
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend"])
    assert [job["jobUnionId"] for job in jobs] == ["9"]
    assert seen_keywords == ["frontend", None]


def test_collect_jobs_filters_interns_from_experienced():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/official/job/getJobList":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {
                                "jobUnionId": "1",
                                "name": "Frontend Expert",
                                "refreshTime": 2000,
                                "jobType": "3",
                                "jobSpecialCode": "5",
                            },
                            {
                                "jobUnionId": "2",
                                "name": "Frontend Intern",
                                "refreshTime": 3000,
                                "jobType": "2",
                                "jobSpecialCode": "6",
                            },
                        ],
                        "page": {"totalPage": 1},
                    },
                    "status": 1,
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend"])
    assert [job["jobUnionId"] for job in jobs] == ["1"]


def test_get_job_detail_returns_nested_data():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/official/job/getJobDetail":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {"jobUnionId": "123"}
            return httpx.Response(200, json={"data": {"jobUnionId": "123", "name": "Role"}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    detail = client.get_job_detail(variant="campus", job_id="123")
    assert detail["jobUnionId"] == "123"


def test_detail_url_includes_campus_highlight():
    client = MeituanOfficialClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert (
        client.detail_url(variant="campus", job_id="123")
        == "https://zhaopin.meituan.com/web/position/detail?jobUnionId=123&highlightType=campus"
    )


def test_detail_url_includes_social_highlight():
    client = MeituanOfficialClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert (
        client.detail_url(variant="experienced", job_id="123")
        == "https://zhaopin.meituan.com/web/position/detail?jobUnionId=123&highlightType=social"
    )
