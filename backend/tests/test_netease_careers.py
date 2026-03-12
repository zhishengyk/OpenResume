import json
from urllib.parse import parse_qs

import httpx

from openresume_api.career_collectors.providers.netease_careers import NeteaseCareerClient


def build_client(handler, *, max_pages: int = 3, page_size: int = 20):
    transport = httpx.MockTransport(handler)
    return NeteaseCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_collect_hr163_jobs_uses_work_type_by_variant():
    observed_work_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/hr163/position/queryPage":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        body = json.loads(request.content.decode("utf-8"))
        observed_work_types.append(str(body.get("workType")))
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "total": 1,
                    "list": [{"id": "101", "name": "Frontend Engineer", "updateTime": 1773238633000}],
                },
            },
        )

    client = build_client(handler, max_pages=1, page_size=20)
    social = client.collect_jobs(variant="experienced", keywords=["frontend"])
    intern = client.collect_jobs(variant="internship", keywords=["frontend"])

    assert [item["id"] for item in social] == ["101"]
    assert [item["id"] for item in intern] == ["101"]
    assert observed_work_types == ["0", "1"]


def test_collect_campus_jobs_resolves_project_id_and_filters_keyword():
    observed_project_ids: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/campuspc/project/navigation/list":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {"title": "应届生", "link": "/app/job/position?id=69"},
                        {"title": "实习生", "link": "/app/job/position?id=70"},
                    ],
                },
            )
        if request.url.path == "/api/campuspc/position/getJobList":
            query = parse_qs(request.url.query.decode("utf-8"))
            observed_project_ids.append(query.get("projectId", [""])[0])
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "total": 2,
                        "list": [
                            {"id": "c-1", "positionName": "AI 前端开发工程师", "positionDescription": "AI product"},
                            {"id": "c-2", "positionName": "后端开发工程师", "positionDescription": "Backend"},
                        ],
                    },
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["前端"])
    assert [item["id"] for item in jobs] == ["c-1"]
    assert observed_project_ids == ["69"]
