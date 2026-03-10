import json

import httpx

from openresume_api.career_collectors.providers.tencent_joinqq import TencentJoinQQClient


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return TencentJoinQQClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def _mapping_payload():
    return {
        "status": 0,
        "data": [
            {
                "recruitType": 1,
                "subProjectList": [
                    {"id": 1, "projectName": "\u5e94\u5c4a\u6bd5\u4e1a\u751f"},
                ],
            },
            {
                "recruitType": 2,
                "subProjectList": [
                    {"id": 2, "projectName": "\u5e94\u5c4a\u5b9e\u4e60"},
                    {"id": 104, "projectName": "\u65e5\u5e38\u5b9e\u4e60"},
                ],
            },
            {
                "recruitType": 999,
                "subProjectList": [
                    {"id": 14, "projectName": "\u9752\u4e91\u8ba1\u5212-\u5e94\u5c4a\u751f"},
                    {"id": 20, "projectName": "\u9752\u4e91\u8ba1\u5212-\u5b9e\u4e60\u751f"},
                    {"id": 16, "projectName": "\u6280\u672f\u7814\u53d1\u63d0\u524d\u6279"},
                ],
            },
        ],
    }


def test_collect_jobs_returns_empty_for_experienced():
    called = {"value": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["value"] = True
        return httpx.Response(500)

    client = build_client(handler)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend"])
    assert jobs == []
    assert called["value"] is False


def test_collect_jobs_uses_campus_project_mapping_ids():
    observed_mapping_ids: list[list[int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/position/getProjectMapping":
            return httpx.Response(200, json=_mapping_payload())
        if request.url.path == "/api/v1/position/searchPosition":
            body = json.loads((request.content or b"{}").decode("utf-8"))
            observed_mapping_ids.append(body.get("projectMappingIdList") or [])
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "data": {
                        "count": 1,
                        "positionList": [
                            {
                                "postId": "101",
                                "positionTitle": "Campus Frontend Engineer",
                            }
                        ],
                    },
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend"])
    assert len(jobs) == 1
    assert jobs[0]["postId"] == "101"
    assert observed_mapping_ids
    assert sorted(observed_mapping_ids[0]) == [1, 14, 16]


def test_collect_jobs_uses_internship_project_mapping_ids():
    observed_mapping_ids: list[list[int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/position/getProjectMapping":
            return httpx.Response(200, json=_mapping_payload())
        if request.url.path == "/api/v1/position/searchPosition":
            body = json.loads((request.content or b"{}").decode("utf-8"))
            observed_mapping_ids.append(body.get("projectMappingIdList") or [])
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "data": {"count": 0, "positionList": []},
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="internship", keywords=["frontend"])
    assert jobs == []
    assert observed_mapping_ids
    assert sorted(observed_mapping_ids[0]) == [2, 20, 104]


def test_collect_jobs_expands_chinese_keyword_and_dedupes():
    requested_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/position/getProjectMapping":
            return httpx.Response(200, json=_mapping_payload())
        if request.url.path == "/api/v1/position/searchPosition":
            body = json.loads((request.content or b"{}").decode("utf-8"))
            keyword = str(body.get("keyword") or "")
            requested_keywords.append(keyword)
            if keyword == "frontend engineer":
                return httpx.Response(
                    200,
                    json={
                        "status": 0,
                        "data": {
                            "count": 1,
                            "positionList": [
                                {
                                    "postId": "102",
                                    "positionTitle": "Frontend Engineer",
                                }
                            ],
                        },
                    },
                )
            if keyword == "\u524d\u7aef\u5de5\u7a0b\u5e08":
                return httpx.Response(
                    200,
                    json={
                        "status": 0,
                        "data": {
                            "count": 1,
                            "positionList": [
                                {
                                    "postId": "102",
                                    "positionTitle": "Frontend Engineer",
                                }
                            ],
                        },
                    },
                )
            return httpx.Response(
                200,
                json={"status": 0, "data": {"count": 0, "positionList": []}},
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["\u524d\u7aef\u5de5\u7a0b\u5e08"])
    assert len(jobs) == 1
    assert jobs[0]["postId"] == "102"
    assert "\u524d\u7aef\u5de5\u7a0b\u5e08" in requested_keywords
    assert "frontend engineer" in requested_keywords
