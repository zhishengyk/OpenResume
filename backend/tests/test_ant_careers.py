import json

import httpx

from openresume_api.career_collectors.providers.ant_careers import AntCareerClient


def build_client(handler, *, max_pages: int = 5, page_size: int = 10, page_worker_count: int = 3):
    transport = httpx.MockTransport(handler)
    return AntCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        page_worker_count=page_worker_count,
        transport=transport,
    )


def test_collect_jobs_fetches_parallel_pages_with_limit_budget():
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/searchCondition/list":
            return httpx.Response(200, json={"content": []})
        if request.url.path != "/api/social/position/search":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        page_index = int(payload["pageIndex"])
        seen_pages.append(page_index)
        if page_index == 1:
            items = [{"id": f"job-{index}", "publishTime": "2026-03-10T00:00:00Z"} for index in range(10)]
        elif page_index == 2:
            items = [{"id": f"job-{10 + index}", "publishTime": "2026-03-10T00:00:00Z"} for index in range(10)]
        elif page_index == 3:
            items = [{"id": f"job-{20 + index}", "publishTime": "2026-03-10T00:00:00Z"} for index in range(5)]
        else:
            raise AssertionError(f"unexpected page {page_index}")
        return httpx.Response(
            200,
            json={"content": items, "totalCount": 25},
        )

    client = build_client(handler, max_pages=5, page_size=10, page_worker_count=3)
    jobs = client.collect_jobs(variant="experienced", keywords=["cpp"], limit=25)

    assert len(jobs) == 25
    assert sorted(seen_pages) == [1, 2, 3]

