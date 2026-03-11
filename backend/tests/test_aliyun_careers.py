import json

import httpx

from openresume_api.career_collectors.providers.aliyun_careers import (
    AliyunCareersClient,
    VARIANT_CONFIGS,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return AliyunCareersClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_channels():
    assert VARIANT_CONFIGS["experienced"].channel == "aliyun_group_official_site"
    assert VARIANT_CONFIGS["campus"].channel == "aliyun_campus_group_official_site"
    assert VARIANT_CONFIGS["campus"].category_type == "freshman"
    assert VARIANT_CONFIGS["internship"].category_type == "internship"


def test_collect_jobs_dedupes_across_keywords():
    seen_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            html = '<script>window.__sysconfig={__token__:"token-123"};</script>'
            return httpx.Response(200, text=html)
        if request.url.path == "/searchCondition/list":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/position/search":
            payload = json.loads(request.content.decode("utf-8"))
            keyword = payload.get("keyword", "")
            seen_keywords.append(keyword)
            if keyword == "frontend":
                data = {
                    "content": {
                        "totalCount": 1,
                        "datas": [{"id": "1", "name": "Frontend A", "publishTime": 1000}],
                    }
                }
                return httpx.Response(200, json=data)
            if keyword == "react":
                data = {
                    "content": {
                        "totalCount": 2,
                        "datas": [
                            {"id": "1", "name": "Frontend A", "publishTime": 1000},
                            {"id": "2", "name": "Frontend B", "publishTime": 2000},
                        ],
                    }
                }
                return httpx.Response(200, json=data)
            raise AssertionError(f"unexpected keyword: {keyword}")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=2, page_size=50)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend", "frontend", "react"])
    assert [job["id"] for job in jobs] == ["2", "1"]
    assert seen_keywords == ["frontend", "react"]


def test_collect_jobs_falls_back_to_empty_keyword():
    seen_keywords: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            html = '<script>window.__sysconfig={__token__:"token-456"};</script>'
            return httpx.Response(200, text=html)
        if request.url.path == "/searchCondition/list":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/position/search":
            payload = json.loads(request.content.decode("utf-8"))
            seen_keywords.append(payload.get("keyword"))
            if payload.get("keyword") == "frontend":
                return httpx.Response(200, json={"content": {"totalCount": 0, "datas": []}})
            if "keyword" not in payload:
                return httpx.Response(
                    200,
                    json={
                        "content": {
                            "totalCount": 1,
                            "datas": [{"id": "9", "name": "Fallback Role", "publishTime": 3000}],
                        }
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=50)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend"])
    assert len(jobs) == 1
    assert jobs[0]["id"] == "9"
    assert seen_keywords == ["frontend", None]


def test_collect_jobs_includes_csrf_in_query_and_headers():
    observed = {"csrf_query": "", "csrf_header": "", "referer": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text='{"__token__":"csrf-token"}')
        if request.url.path == "/searchCondition/list":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/position/search":
            observed["csrf_query"] = request.url.params.get("_csrf", "")
            observed["csrf_header"] = request.headers.get("x-csrf-token", "")
            observed["referer"] = request.headers.get("referer", "")
            return httpx.Response(200, json={"content": {"totalCount": 0, "datas": []}})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    client.collect_jobs(variant="campus", keywords=["frontend"])
    assert observed["csrf_query"] == "csrf-token"
    assert observed["csrf_header"] == "csrf-token"
    assert "campusType=freshman" in observed["referer"]


def test_detail_url_prefers_position_url_and_handles_relative_paths():
    client = AliyunCareersClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert (
        client.detail_url(
            variant="experienced",
            job_id="1",
            position_url="https://careers.aliyun.com/custom/position/1",
        )
        == "https://careers.aliyun.com/custom/position/1"
    )
    assert (
        client.detail_url(
            variant="experienced",
            job_id="1",
            position_url="/off-campus/position-detail?positionId=1",
        )
        == "https://careers.aliyun.com/off-campus/position-detail?positionId=1"
    )
    assert (
        client.detail_url(variant="internship", job_id="2")
        == "https://careers.aliyun.com/campus/position-detail?positionId=2&campusType=internship"
    )


def test_search_payload_includes_category_type_for_campus():
    client = AliyunCareersClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    config = VARIANT_CONFIGS["campus"]
    payload = client._search_payload(config=config, current=1, keyword="")
    assert payload["channel"] == "aliyun_campus_group_official_site"
    assert payload["language"] == "zh"
    assert payload["pageIndex"] == 1
    assert payload["pageSize"] == 20
    assert payload["categoryType"] == "freshman"
    assert "keyword" not in payload
