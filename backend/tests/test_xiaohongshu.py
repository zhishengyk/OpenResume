import json

import httpx

from openresume_api.career_collectors.providers.xiaohongshu import (
    VARIANT_CONFIGS,
    XiaohongshuClient,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return XiaohongshuClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_recruit_types():
    assert VARIANT_CONFIGS["experienced"].recruit_type == "social"
    assert VARIANT_CONFIGS["campus"].recruit_type == "campus"
    assert VARIANT_CONFIGS["internship"].recruit_type == "intern"


def test_collect_jobs_dedupes_across_keywords_and_sorts_by_publish_time():
    seen_keywords: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/websiterecruit/position/pageQueryPosition":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        seen_keywords.append(payload.get("positionName"))
        keyword = payload.get("positionName", "")
        if keyword == "frontend":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "total": 1,
                        "list": [
                            {
                                "positionId": "1",
                                "positionName": "Frontend Engineer",
                                "publishTime": "2026-03-01",
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
                        "total": 2,
                        "list": [
                            {
                                "positionId": "1",
                                "positionName": "Frontend Engineer",
                                "publishTime": "2026-03-01",
                            },
                            {
                                "positionId": "2",
                                "positionName": "React Engineer",
                                "publishTime": "2026-03-02",
                            },
                        ],
                    }
                },
            )
        raise AssertionError(f"unexpected payload: {payload}")

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(
        variant="experienced",
        keywords=["frontend", "react"],
    )

    assert [job["positionId"] for job in jobs] == ["2", "1"]
    assert seen_keywords == ["frontend", "react"]


def test_collect_jobs_falls_back_to_empty_keyword():
    seen_keywords: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/websiterecruit/position/pageQueryPosition":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        seen_keywords.append(payload.get("positionName"))
        if payload.get("positionName") == "frontend":
            return httpx.Response(200, json={"data": {"total": 0, "list": []}})
        if "positionName" not in payload:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "total": 1,
                        "list": [
                            {
                                "positionId": "9",
                                "positionName": "Fallback Role",
                                "publishTime": "2026-03-03",
                            }
                        ],
                    }
                },
            )
        raise AssertionError(f"unexpected payload: {payload}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend"])

    assert [job["positionId"] for job in jobs] == ["9"]
    assert seen_keywords == ["frontend", None]


def test_matches_variant_separates_campus_and_internship_titles():
    client = XiaohongshuClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    campus_role = {"positionName": "Frontend Engineer"}
    intern_role = {"positionName": "Frontend Intern"}

    assert client._matches_variant(variant="experienced", item=campus_role) is True
    assert client._matches_variant(variant="experienced", item=intern_role) is False
    assert client._matches_variant(variant="campus", item=campus_role) is True
    assert client._matches_variant(variant="campus", item=intern_role) is False
    assert client._matches_variant(variant="internship", item=intern_role) is True


def test_detail_url_uses_expected_route():
    client = XiaohongshuClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )

    assert (
        client.detail_url(variant="internship", job_id="42")
        == "https://job.xiaohongshu.com/campus/position/42"
    )
