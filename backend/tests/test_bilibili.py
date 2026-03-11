import json

import httpx

from openresume_api.career_collectors.providers.bilibili import (
    VARIANT_CONFIGS,
    BilibiliClient,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return BilibiliClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_channels():
    assert VARIANT_CONFIGS["experienced"].channel == "social"
    assert VARIANT_CONFIGS["experienced"].recruit_type == 0
    assert VARIANT_CONFIGS["campus"].channel == "campus"
    assert VARIANT_CONFIGS["campus"].recruit_type == 1
    assert VARIANT_CONFIGS["internship"].recruit_type == 0


def test_collect_jobs_fetches_csrf_and_reuses_headers():
    csrf_calls: list[dict[str, str]] = []
    list_calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/auth/v1/csrf/token":
            csrf_calls.append(
                {
                    "channel": request.headers["X-Channel"],
                    "app_key": request.headers["X-AppKey"],
                    "user_type": request.headers["X-UserType"],
                }
            )
            return httpx.Response(200, json={"data": "csrf-123"})

        if request.method == "POST" and request.url.path == "/api/campus/position/positionList":
            payload = json.loads(request.content.decode("utf-8"))
            list_calls.append(
                {
                    "channel": request.headers["X-Channel"],
                    "csrf": request.headers["X-CSRF"],
                    "keyword": payload.get("positionName"),
                    "page_num": payload["pageNum"],
                    "page_size": payload["pageSize"],
                    "recruit_type": payload["recruitType"],
                    "has_session_id": bool(payload.get("ajSessionId")),
                }
            )
            keyword = payload.get("positionName", "")
            if keyword == "frontend":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "list": [
                                {
                                    "id": "1",
                                    "positionName": "Frontend Engineer",
                                    "positionTypeName": "\u6b63\u5f0f",
                                    "pushTime": "2026-03-01 09:00:00",
                                }
                            ]
                        }
                    },
                )
            if keyword == "react":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "list": [
                                {
                                    "id": "1",
                                    "positionName": "Frontend Engineer",
                                    "positionTypeName": "\u6b63\u5f0f",
                                    "pushTime": "2026-03-01 09:00:00",
                                },
                                {
                                    "id": "2",
                                    "positionName": "React Engineer",
                                    "positionTypeName": "\u6b63\u5f0f",
                                    "pushTime": "2026-03-02 09:00:00",
                                },
                            ]
                        }
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(
        variant="campus",
        keywords=["frontend", "react"],
    )

    assert [job["id"] for job in jobs] == ["2", "1"]
    assert csrf_calls == [
        {
            "channel": "campus",
            "app_key": "ops.ehr-api.auth",
            "user_type": "2",
        }
    ]
    assert list_calls == [
        {
            "channel": "campus",
            "csrf": "csrf-123",
            "keyword": "frontend",
            "page_num": 1,
            "page_size": 20,
            "recruit_type": 1,
            "has_session_id": True,
        },
        {
            "channel": "campus",
            "csrf": "csrf-123",
            "keyword": "react",
            "page_num": 1,
            "page_size": 20,
            "recruit_type": 1,
            "has_session_id": True,
        },
    ]


def test_collect_jobs_falls_back_to_empty_keyword():
    seen_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/auth/v1/csrf/token":
            return httpx.Response(200, json={"data": "csrf-123"})

        if request.method == "POST" and request.url.path == "/api/srs/position/positionList":
            payload = json.loads(request.content.decode("utf-8"))
            seen_keywords.append(payload.get("positionName", ""))
            keyword = payload.get("positionName", "")
            if keyword == "frontend":
                return httpx.Response(200, json={"data": {"list": []}})
            if keyword == "":
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "list": [
                                {
                                    "id": "9",
                                    "positionName": "Fallback Role",
                                    "positionTypeName": "\u6b63\u5f0f",
                                    "pushTime": "2026-03-03 09:00:00",
                                }
                            ]
                        }
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend"])

    assert [job["id"] for job in jobs] == ["9"]
    assert seen_keywords == ["frontend", ""]


def test_matches_variant_separates_campus_and_internship():
    client = BilibiliClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    campus_role = {
        "positionName": "Frontend Engineer",
        "positionTypeName": "\u6b63\u5f0f",
    }
    internship_role = {
        "positionName": "Frontend Intern",
        "positionTypeName": "\u5b9e\u4e60",
    }

    assert client._matches_variant(variant="experienced", item=campus_role) is True
    assert client._matches_variant(variant="experienced", item=internship_role) is False
    assert client._matches_variant(variant="campus", item=campus_role) is True
    assert client._matches_variant(variant="campus", item=internship_role) is False
    assert client._matches_variant(variant="internship", item=internship_role) is True


def test_detail_url_uses_expected_route():
    client = BilibiliClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    assert (
        client.detail_url(variant="experienced", job_id="42")
        == "https://jobs.bilibili.com/social/positions/42"
    )
