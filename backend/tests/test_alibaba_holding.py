import json

import httpx

from openresume_api.career_collectors.providers.alibaba_holding import (
    AlibabaHoldingCareerClient,
    VARIANT_CONFIGS,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return AlibabaHoldingCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_channels():
    assert VARIANT_CONFIGS["experienced"].channel == "kgjt_group_official_site"
    assert VARIANT_CONFIGS["campus"].channel == "kgjt_campus_group_official_site"
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
                return httpx.Response(
                    200,
                    json={
                        "content": {
                            "totalCount": 1,
                            "datas": [{"id": "1", "name": "Frontend A", "publishTime": 1000}],
                        }
                    },
                )
            if keyword == "react":
                return httpx.Response(
                    200,
                    json={
                        "content": {
                            "totalCount": 2,
                            "datas": [
                                {"id": "1", "name": "Frontend A", "publishTime": 1000},
                                {"id": "2", "name": "Frontend B", "publishTime": 2000},
                            ],
                        }
                    },
                )
            raise AssertionError(f"unexpected keyword: {keyword}")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=2, page_size=50)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend", "react"])
    assert [job["id"] for job in jobs] == ["2", "1"]
    assert seen_keywords == ["frontend", "react"]


def test_detail_url_uses_expected_domain():
    client = AlibabaHoldingCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert (
        client.detail_url(variant="internship", job_id="2")
        == "https://talent-holding.alibaba.com/campus/position-detail?positionId=2&campusType=internship"
    )
