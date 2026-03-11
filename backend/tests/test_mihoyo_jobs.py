import json

import httpx

from openresume_api.career_collectors.providers.mihoyo_jobs import (
    VARIANT_CONFIGS,
    MihoyoJobsClient,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return MihoyoJobsClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_public_routes():
    assert VARIANT_CONFIGS["experienced"].entry_url == "https://jobs.mihoyo.com/m/#/position"
    assert VARIANT_CONFIGS["experienced"].hire_type == 0
    assert VARIANT_CONFIGS["campus"].entry_url == "https://jobs.mihoyo.com/m/#/campus/position"
    assert VARIANT_CONFIGS["campus"].hire_type == 1


def test_collect_jobs_posts_expected_payloads_and_dedupes_across_keywords():
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.path != "/ats-portal/v1/job/list":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        seen_payloads.append(payload)
        keyword = payload.get("jobName", "")
        if keyword == "frontend":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [{"id": "1", "title": "Frontend Engineer", "jobNatureId": "1"}],
                        "total": 1,
                    }
                },
            )
        if keyword == "react":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {"id": "1", "title": "Frontend Engineer", "jobNatureId": "1"},
                            {"id": "2", "title": "React Engineer", "jobNatureId": "1"},
                        ],
                        "total": 2,
                    }
                },
            )
        raise AssertionError(f"unexpected payload: {payload}")

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(
        variant="experienced",
        keywords=["frontend", "react"],
    )

    assert [job["id"] for job in jobs] == ["1", "2"]
    assert seen_payloads == [
        {
            "jobName": "frontend",
            "pageNo": 1,
            "pageSize": 20,
            "channelDetailIds": [1],
            "hireType": 0,
        },
        {
            "jobName": "react",
            "pageNo": 1,
            "pageSize": 20,
            "channelDetailIds": [1],
            "hireType": 0,
        },
    ]


def test_collect_jobs_falls_back_to_empty_keyword():
    seen_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.path != "/ats-portal/v1/job/list":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        seen_keywords.append(payload.get("jobName", ""))
        if payload.get("jobName") == "frontend":
            return httpx.Response(200, json={"data": {"list": [], "total": 0}})
        if payload.get("jobName") == "":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [{"id": "9", "title": "Fallback Role", "jobNatureId": "3"}],
                        "total": 1,
                    }
                },
            )
        raise AssertionError(f"unexpected payload: {payload}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="internship", keywords=["frontend"])

    assert [job["id"] for job in jobs] == ["9"]
    assert seen_keywords == ["frontend", ""]


def test_fetch_detail_posts_expected_payload():
    observed_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.path != "/ats-portal/v1/job/info":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        observed_payloads.append(payload)
        return httpx.Response(200, json={"data": {"id": "7242", "title": "Role"}})

    client = build_client(handler, max_pages=1, page_size=20)
    detail = client.fetch_detail(variant="campus", job_id="7242")

    assert detail == {"id": "7242", "title": "Role"}
    assert observed_payloads == [
        {
            "id": "7242",
            "channelDetailIds": [1],
            "hireType": 1,
        }
    ]


def test_matches_variant_separates_job_nature_ids():
    client = MihoyoJobsClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    campus_role = {"title": "Graduate Engineer", "jobNatureId": "1"}
    internship_role = {"title": "Engine Intern", "jobNatureId": "3"}
    shared_role = {"title": "Researcher", "jobNatureId": "4"}

    assert client._matches_variant(variant="experienced", item=campus_role) is True
    assert client._matches_variant(variant="experienced", item=internship_role) is False
    assert client._matches_variant(variant="campus", item=campus_role) is True
    assert client._matches_variant(variant="campus", item=internship_role) is False
    assert client._matches_variant(variant="campus", item=shared_role) is True
    assert client._matches_variant(variant="internship", item=internship_role) is True
    assert client._matches_variant(variant="internship", item=shared_role) is True


def test_detail_url_uses_hash_route():
    client = MihoyoJobsClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    assert (
        client.detail_url(variant="campus", job_id="42")
        == "https://jobs.mihoyo.com/m/#/campus/position/42"
    )
