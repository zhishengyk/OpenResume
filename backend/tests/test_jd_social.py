from urllib.parse import parse_qs

import httpx

from openresume_api.career_collectors.providers.jd_social import JdSocialClient


def build_client(handler, *, max_pages: int = 5, page_size: int = 10, page_worker_count: int = 3):
    transport = httpx.MockTransport(handler)
    return JdSocialClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        page_worker_count=page_worker_count,
        transport=transport,
    )


def test_collect_jobs_limits_parallel_page_budget():
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="ok")
        if request.url.path != "/web/job/job_list":
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        form = parse_qs(request.content.decode("utf-8"))
        page_index = int(form["pageIndex"][0])
        seen_pages.append(page_index)
        if page_index == 1:
            items = [{"requirementId": f"job-{index}", "publishTime": index} for index in range(10)]
        elif page_index == 2:
            items = [{"requirementId": f"job-{10 + index}", "publishTime": 10 + index} for index in range(10)]
        elif page_index == 3:
            items = [{"requirementId": f"job-{20 + index}", "publishTime": 20 + index} for index in range(5)]
        else:
            raise AssertionError(f"unexpected page {page_index}")
        return httpx.Response(200, json=items)

    client = build_client(handler, max_pages=5, page_size=10, page_worker_count=3)
    jobs = client.collect_jobs(keywords=["cpp"], limit=25)

    assert len(jobs) == 25
    assert sorted(seen_pages) == [1, 2, 3]
    assert jobs[0]["requirementId"] == "job-24"

