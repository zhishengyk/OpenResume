import json
import time

import httpx

from openresume_api.career_collectors.providers.meituan_official import (
    MeituanOfficialClient,
)


def build_client(
    handler,
    *,
    max_pages: int = 5,
    page_size: int = 50,
    page_worker_count: int = 1,
):
    transport = httpx.MockTransport(handler)
    return MeituanOfficialClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        page_worker_count=page_worker_count,
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


def test_collect_jobs_applies_limit_after_keyword_dedupe():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/official/job/getJobList":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        keyword = payload.get("keywords", "")
        if keyword == "frontend":
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
        if keyword == "react":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {"jobUnionId": "2", "name": "Frontend B", "refreshTime": 2000},
                            {"jobUnionId": "3", "name": "Frontend C", "refreshTime": 3000},
                        ],
                        "page": {"totalPage": 1},
                    },
                    "status": 1,
                },
            )
        raise AssertionError(f"unexpected payload: {payload}")

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(
        variant="campus",
        keywords=["frontend", "react"],
        limit=2,
    )
    assert [job["jobUnionId"] for job in jobs] == ["2", "1"]


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


def test_collect_jobs_limits_pages_and_keeps_sorted_results():
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/official/job/getJobList":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        current = payload["page"]["pageNo"]
        seen_pages.append(current)
        if current == 1:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {"jobUnionId": "a", "name": "Job A", "refreshTime": 5000},
                            {"jobUnionId": "b", "name": "Job B", "refreshTime": 4000},
                        ],
                        "page": {"totalPage": 4},
                    },
                    "status": 1,
                },
            )
        if current == 2:
            time.sleep(0.03)
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {"jobUnionId": "c", "name": "Job C", "refreshTime": 3000},
                            {"jobUnionId": "d", "name": "Job D", "refreshTime": 2000},
                        ],
                        "page": {"totalPage": 4},
                    },
                    "status": 1,
                },
            )
        if current == 3:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {"jobUnionId": "e", "name": "Job E", "refreshTime": 1000},
                            {"jobUnionId": "f", "name": "Job F", "refreshTime": 500},
                        ],
                        "page": {"totalPage": 4},
                    },
                    "status": 1,
                },
            )
        raise AssertionError(f"unexpected page request: {current}")

    client = build_client(
        handler,
        max_pages=4,
        page_size=2,
        page_worker_count=3,
    )
    jobs = client.collect_jobs(
        variant="campus",
        keywords=["frontend"],
        limit=5,
    )
    assert [job["jobUnionId"] for job in jobs] == ["a", "b", "c", "d", "e"]
    assert seen_pages == [1, 2, 3]


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


def test_get_job_details_degrades_single_job_failures():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/official/job/getJobDetail":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        if payload == {"jobUnionId": "good"}:
            return httpx.Response(200, json={"data": {"jobUnionId": "good", "name": "Role"}})
        if payload == {"jobUnionId": "bad"}:
            return httpx.Response(500, json={"message": "boom"})
        raise AssertionError(f"unexpected payload: {payload}")

    client = build_client(handler, max_pages=1, page_size=20)
    details = client.get_job_details(
        variant="campus",
        job_ids=["good", "bad"],
        worker_count=2,
    )
    assert details["good"]["jobUnionId"] == "good"
    assert details["bad"] == {}


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
