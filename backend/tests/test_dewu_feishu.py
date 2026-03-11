import json

import httpx

from openresume_api.career_collectors.providers.dewu_feishu import (
    VARIANT_CONFIGS,
    DewuFeishuClient,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return DewuFeishuClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_domains():
    assert VARIANT_CONFIGS["experienced"].base_url == "https://poizon.jobs.feishu.cn"
    assert VARIANT_CONFIGS["experienced"].website_path == "index"
    assert VARIANT_CONFIGS["campus"].base_url == "https://campus.dewu.com"
    assert VARIANT_CONFIGS["campus"].website_path == "578078"


def test_collect_jobs_dedupes_across_keywords_after_csrf():
    seen_keywords: list[str] = []
    observed_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/csrf/token":
            observed_headers.append(
                {
                    "website_path": request.headers["website-path"],
                    "csrf": request.headers["x-csrf-token"],
                    "portal_channel": request.headers["Portal-Channel"],
                }
            )
            return httpx.Response(200, json={"data": {"token": "csrf-123"}})

        if request.method == "POST" and request.url.path == "/api/v1/search/job/posts":
            payload = json.loads(request.content.decode("utf-8"))
            seen_keywords.append(payload["keyword"])
            assert request.headers["x-csrf-token"] == "csrf-123"
            keyword = payload["keyword"]
            if keyword == "frontend":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "count": 1,
                            "job_post_list": [
                                {
                                    "id": "1",
                                    "title": "Frontend Engineer",
                                    "publish_time": 1000,
                                    "recruit_type": {
                                        "id": "101",
                                        "name": "\u6b63\u5f0f",
                                        "parent": {"id": "1", "name": "\u793e\u62db"},
                                    },
                                }
                            ],
                        }
                    },
                )
            if keyword == "react":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "count": 2,
                            "job_post_list": [
                                {
                                    "id": "1",
                                    "title": "Frontend Engineer",
                                    "publish_time": 1000,
                                    "recruit_type": {
                                        "id": "101",
                                        "name": "\u6b63\u5f0f",
                                        "parent": {"id": "1", "name": "\u793e\u62db"},
                                    },
                                },
                                {
                                    "id": "2",
                                    "title": "React Engineer",
                                    "publish_time": 2000,
                                    "recruit_type": {
                                        "id": "101",
                                        "name": "\u6b63\u5f0f",
                                        "parent": {"id": "1", "name": "\u793e\u62db"},
                                    },
                                },
                            ],
                        }
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(
        variant="experienced",
        keywords=["frontend", "react"],
    )

    assert [job["id"] for job in jobs] == ["2", "1"]
    assert seen_keywords == ["frontend", "react"]
    assert observed_headers == [
        {
            "website_path": "index",
            "csrf": "undefined",
            "portal_channel": "saas-career",
        }
    ]


def test_collect_jobs_falls_back_to_empty_keyword():
    seen_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/csrf/token":
            return httpx.Response(200, json={"data": {"token": "csrf-123"}})

        if request.method == "POST" and request.url.path == "/api/v1/search/job/posts":
            payload = json.loads(request.content.decode("utf-8"))
            seen_keywords.append(payload["keyword"])
            if payload["keyword"] == "frontend":
                return httpx.Response(200, json={"data": {"count": 0, "job_post_list": []}})
            if payload["keyword"] == "":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "count": 1,
                            "job_post_list": [
                                {
                                    "id": "9",
                                    "title": "Fallback Role",
                                    "publish_time": 3000,
                                    "recruit_type": {
                                        "id": "201",
                                        "name": "\u6b63\u5f0f",
                                        "parent": {"id": "2", "name": "\u6821\u62db"},
                                    },
                                }
                            ],
                        }
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend"])

    assert [job["id"] for job in jobs] == ["9"]
    assert seen_keywords == ["frontend", ""]


def test_fetch_detail_returns_nested_job_post_detail():
    observed_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/csrf/token":
            return httpx.Response(200, json={"data": {"token": "csrf-123"}})

        if request.method == "GET" and request.url.path == "/api/v1/job/posts/123":
            observed_params.update(dict(request.url.params))
            assert request.headers["x-csrf-token"] == "csrf-123"
            return httpx.Response(
                200,
                json={"data": {"job_post_detail": {"id": "123", "title": "Role"}}},
            )

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    detail = client.fetch_detail(variant="campus", job_id="123")

    assert detail == {"id": "123", "title": "Role"}
    assert observed_params == {
        "portal_type": "6",
        "source_job_post_id": "123",
        "with_recommend": "false",
    }


def test_matches_variant_separates_experienced_campus_and_internship():
    client = DewuFeishuClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    experienced_role = {
        "title": "Frontend Engineer",
        "recruit_type": {
            "id": "101",
            "name": "\u6b63\u5f0f",
            "parent": {"id": "1", "name": "\u793e\u62db"},
        },
    }
    campus_role = {
        "title": "Graduate Engineer",
        "recruit_type": {
            "id": "201",
            "name": "\u6b63\u5f0f",
            "parent": {"id": "2", "name": "\u6821\u62db"},
        },
    }
    intern_role = {
        "title": "Frontend Intern",
        "recruit_type": {
            "id": "202",
            "name": "\u5b9e\u4e60",
            "parent": {"id": "2", "name": "\u6821\u62db"},
        },
    }

    assert client._matches_variant(variant="experienced", item=experienced_role) is True
    assert client._matches_variant(variant="experienced", item=intern_role) is False
    assert client._matches_variant(variant="campus", item=campus_role) is True
    assert client._matches_variant(variant="campus", item=intern_role) is False
    assert client._matches_variant(variant="internship", item=intern_role) is True


def test_detail_url_uses_expected_variant_domain():
    client = DewuFeishuClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    assert (
        client.detail_url(variant="internship", job_id="42")
        == "https://campus.dewu.com/578078/position/42/detail"
    )
