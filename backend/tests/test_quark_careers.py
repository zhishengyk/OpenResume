import json

import httpx

from openresume_api.career_collectors.providers.quark_careers import (
    QuarkCareerClient,
    VARIANT_CONFIGS,
)


def build_client(handler, *, max_pages: int = 3, page_size: int = 20):
    transport = httpx.MockTransport(handler)
    return QuarkCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_use_expected_channels():
    assert VARIANT_CONFIGS["experienced"].channel == "Quark_group_official_site"
    assert VARIANT_CONFIGS["campus"].channel == "Quark_campus_group_official_site"
    assert VARIANT_CONFIGS["campus"].category_type == "freshman"
    assert VARIANT_CONFIGS["internship"].category_type == "internship"


def test_collect_jobs_uses_key_field_in_search_payload():
    observed_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            html = '<script>window.__sysconfig={__token__:"token-xyz"};</script>'
            return httpx.Response(200, text=html)
        if request.url.path == "/searchCondition/list":
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/position/search":
            body = json.loads(request.content.decode("utf-8"))
            observed_payloads.append(body)
            return httpx.Response(
                200,
                json={
                    "content": {
                        "totalCount": 1,
                        "datas": [{"id": "q-1", "name": "Frontend Engineer", "publishTime": 1000}],
                    }
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend"])
    assert [job["id"] for job in jobs] == ["q-1"]
    assert observed_payloads
    payload = observed_payloads[0]
    assert payload["channel"] == "Quark_campus_group_official_site"
    assert payload["categoryType"] == "freshman"
    assert payload["key"] == "frontend"
    assert "keyword" not in payload


def test_detail_url_uses_expected_path_template():
    client = QuarkCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert "off-campus/position-detail" in client.detail_url(variant="experienced", job_id="1")
    assert "campusType=freshman" in client.detail_url(variant="campus", job_id="2")
