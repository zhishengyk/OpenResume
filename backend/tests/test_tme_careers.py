import json

import httpx

from openresume_api.career_collectors.providers.tme_careers import (
    TmeCareerClient,
    VARIANT_CONFIGS,
)


def build_client(handler, *, max_pages: int = 3, page_size: int = 20):
    transport = httpx.MockTransport(handler)
    return TmeCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_use_expected_paths():
    assert VARIANT_CONFIGS["experienced"].list_path == "/api/job/list"
    assert VARIANT_CONFIGS["campus"].list_path == "/api/uc-job/list"
    assert VARIANT_CONFIGS["internship"].detail_path == "/api/uc-job/info"


def test_collect_jobs_filters_campus_and_internship():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/uc-job/list":
            body = json.loads(request.content.decode("utf-8"))
            if body["page"] > 1:
                return httpx.Response(
                    200,
                    json={"code": "200", "data": {"items": [], "_meta": {"page_count": 1}}},
                )
            payload = {
                "code": "200",
                "data": {
                    "items": [
                        {"id": "1", "name": "Campus Role", "job_type_descr": "应届生", "date": "2026-03-10"},
                        {"id": "2", "name": "Intern Role", "job_type_descr": "实习生", "date": "2026-03-11"},
                    ],
                    "_meta": {"total_count": 2, "page_count": 1, "page_size": 20, "current_page": 1},
                },
            }
            return httpx.Response(200, json=payload)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler)
    campus_jobs = client.collect_jobs(variant="campus", keywords=["frontend"])
    internship_jobs = client.collect_jobs(variant="internship", keywords=["frontend"])

    assert [item["id"] for item in campus_jobs] == ["1"]
    assert [item["id"] for item in internship_jobs] == ["2"]


def test_collect_jobs_dedupes_across_keywords():
    requested_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/job/list":
            body = json.loads(request.content.decode("utf-8"))
            keyword = body.get("keyword") or ""
            requested_keywords.append(keyword)
            if keyword == "react":
                items = [{"id": "10", "name": "Frontend Engineer", "date": "2026-03-11"}]
            elif keyword == "typescript":
                items = [
                    {"id": "10", "name": "Frontend Engineer", "date": "2026-03-11"},
                    {"id": "11", "name": "Platform Engineer", "date": "2026-03-10"},
                ]
            else:
                items = []
            return httpx.Response(
                200,
                json={
                    "code": "200",
                    "data": {
                        "items": items,
                        "_meta": {"total_count": len(items), "page_count": 1, "page_size": 20, "current_page": 1},
                    },
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="experienced", keywords=["react", "typescript"])
    assert [item["id"] for item in jobs] == ["10", "11"]
    assert requested_keywords == ["react", "typescript"]


def test_detail_url_uses_info_endpoint():
    client = TmeCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert client.detail_url(variant="experienced", job_id="123").endswith("/api/job/info?id=123")
    assert client.detail_url(variant="campus", job_id="456").endswith("/api/uc-job/info?id=456")
