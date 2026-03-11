import json

import httpx

from openresume_api.career_collectors.providers.jd_campus import JdCampusClient


def build_client(handler, *, max_pages: int = 5, page_size: int = 10, page_worker_count: int = 3):
    transport = httpx.MockTransport(handler)
    return JdCampusClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        page_worker_count=page_worker_count,
        transport=transport,
    )


def test_collect_jobs_fetches_only_pages_required_by_total_and_limit():
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/wx/position/getProjectList":
            return httpx.Response(200, json={"body": []})
        if request.url.path == "/api/wx/position/dict":
            return httpx.Response(200, json={"body": []})
        if request.url.path != "/api/wx/position/page":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        payload = json.loads(request.content.decode("utf-8"))
        page_index = int(payload["pageIndex"])
        seen_pages.append(page_index)
        if page_index == 0:
            items = [{"publishId": f"job-{index}", "publishTime": index} for index in range(10)]
        elif page_index == 1:
            items = [{"publishId": f"job-{10 + index}", "publishTime": 10 + index} for index in range(10)]
        elif page_index == 2:
            items = [{"publishId": f"job-{20 + index}", "publishTime": 20 + index} for index in range(5)]
        else:
            raise AssertionError(f"unexpected page {page_index}")
        return httpx.Response(
            200,
            json={"body": {"items": items, "totalNumber": 25}},
        )

    client = build_client(handler, max_pages=5, page_size=10, page_worker_count=3)
    jobs = client.collect_jobs(variant="campus", keywords=["cpp"], limit=25)

    assert len(jobs) == 25
    assert sorted(seen_pages) == [0, 1, 2]
    assert jobs[0]["publishId"] == "job-24"

