import httpx

from openresume_api.career_collectors.providers.baidu_jobs import (
    BaiduJobClient,
    VARIANT_CONFIGS,
)


def build_client(handler, *, max_pages: int = 3, page_size: int = 20):
    transport = httpx.MockTransport(handler)
    return BaiduJobClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_collect_jobs_parses_initial_data_with_undefined_value():
    html = """
<html><body><script>
window.__INITIAL_DATA__ = {
  "detailData": {"projectType": undefined},
  "listData": {
    "listDetailData": [
      {"postId": "p-1", "name": "校园实习生", "workPlace": "北京市", "workContent": "AI", "serviceCondition": "Python"},
      {"postId": "p-2", "name": "校招前端工程师", "workPlace": "上海市", "workContent": "React", "serviceCondition": "TypeScript"}
    ],
    "total": 2
  }
};
window.prefix = "/jobs";
</script></body></html>
"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = build_client(handler)
    jobs = client.collect_jobs(variant="internship", keywords=["实习"])
    assert len(jobs) == 1
    assert jobs[0]["postId"] == "p-1"


def test_collect_jobs_falls_back_to_empty_keyword():
    html = """
<html><body><script>
window.__INITIAL_DATA__ = {
  "listData": {
    "listDetailData": [
      {"postId": "p-3", "name": "后端工程师", "workPlace": "北京市", "workContent": "Golang", "serviceCondition": "3年以上"}
    ],
    "total": 1
  }
};
window.prefix = "/jobs";
</script></body></html>
"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = build_client(handler)
    jobs = client.collect_jobs(variant="experienced", keywords=["does-not-exist"])
    assert len(jobs) == 1
    assert jobs[0]["postId"] == "p-3"


def test_detail_url_appends_post_id():
    client = BaiduJobClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    url = client.detail_url(variant="campus", job_id="abc123")
    assert url.startswith(VARIANT_CONFIGS["campus"].entry_url)
    assert "postId=abc123" in url
