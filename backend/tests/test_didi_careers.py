import html
import json
from urllib.parse import parse_qs

import httpx

from openresume_api.career_collectors.providers.didi_careers import DidiCareerClient


def build_client(handler, *, max_pages: int = 3, page_size: int = 20):
    transport = httpx.MockTransport(handler)
    return DidiCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def _campus_html(payload: dict) -> str:
    encoded = html.escape(json.dumps(payload, ensure_ascii=False))
    return f'<html><body><input id="init-data" type="hidden" value="{encoded}"></body></html>'


def test_collect_social_jobs_falls_back_to_empty_keyword():
    seen_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/job/front/list"):
            query = parse_qs(request.url.query.decode("utf-8"))
            keyword = query.get("searchText", [""])[0]
            seen_keywords.append(keyword)
            if keyword == "frontend":
                payload = {"data": {"items": [], "total": 0}}
                return httpx.Response(200, json=payload)
            payload = {
                "data": {
                    "items": [{"jdId": "100", "jobName": "Frontend Engineer"}],
                    "total": 1,
                }
            }
            return httpx.Response(200, json=payload)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend"])
    assert len(jobs) == 1
    assert jobs[0]["jdId"] == "100"
    assert seen_keywords == ["frontend", ""]


def test_get_social_job_detail_reads_data_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/job/front/view/100"):
            payload = {
                "data": {
                    "jobName": "Frontend Engineer",
                    "jobDesc": "Build web apps",
                    "qualification": "React TypeScript",
                }
            }
            return httpx.Response(200, json=payload)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler)
    detail = client.get_social_job_detail(job_id="100")
    assert detail["jobName"] == "Frontend Engineer"
    assert detail["qualification"] == "React TypeScript"


def test_collect_campus_jobs_filters_campus_and_internship():
    payload = {
        "org": {"id": "didiglobal", "siteId": 96064},
        "siteId": "96064",
        "jobs": [
            {
                "id": "campus-1",
                "title": "26届春招-前端工程师",
                "commitment": "全职",
                "department": {"name": "研发"},
            },
            {
                "id": "intern-1",
                "title": "日常实习-前端开发",
                "commitment": "实习",
                "department": {"name": "研发"},
            },
        ],
    }
    html_body = _campus_html(payload)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_body)

    client = build_client(handler)
    campus_jobs = client.collect_jobs(variant="campus", keywords=["前端"])
    intern_jobs = client.collect_jobs(variant="internship", keywords=["前端"])

    assert [job["id"] for job in campus_jobs] == ["campus-1"]
    assert [job["id"] for job in intern_jobs] == ["intern-1"]
