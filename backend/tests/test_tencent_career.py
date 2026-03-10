import json

import httpx

from openresume_api.career_collectors.providers.tencent_career import (
    TencentCareerClient,
    VARIANT_CONFIGS,
    parse_tencent_date,
)


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return TencentCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_variant_configs_map_to_expected_attr_ids():
    assert VARIANT_CONFIGS["experienced"].attr_id == "1"
    assert VARIANT_CONFIGS["campus"].attr_id == "2,5"
    assert VARIANT_CONFIGS["internship"].attr_id == "3"


def test_page_size_is_capped_at_50():
    client = TencentCareerClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=5,
        page_size=999,
    )
    assert client.page_size == 50


def test_parse_tencent_date_handles_cn_format():
    result = parse_tencent_date("2026年03月10日")
    assert result is not None
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 10


def test_collect_jobs_dedupes_across_keywords():
    request_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_keywords.append(request.url.params.get("keyword", ""))
        payload = {
            "Code": 200,
            "Data": {
                "Count": 1,
                "Posts": [
                    {
                        "PostId": "1001",
                        "RecruitPostName": "Frontend Engineer",
                        "LastUpdateTime": "2026年03月10日",
                    }
                ],
            },
        }
        return httpx.Response(200, json=payload)

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend", "frontend", "react"])
    assert len(jobs) == 1
    assert jobs[0]["PostId"] == "1001"
    assert request_keywords == ["frontend", "react"]


def test_collect_jobs_expands_chinese_role_keyword():
    request_keywords: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keyword = request.url.params.get("keyword", "")
        request_keywords.append(keyword)
        if keyword == "frontend engineer":
            payload = {
                "Code": 200,
                "Data": {
                    "Count": 1,
                    "Posts": [
                        {
                            "PostId": "2001",
                            "RecruitPostName": "Frontend Engineer",
                            "LastUpdateTime": "2026年3月10日",
                        }
                    ],
                },
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json={"Code": 200, "Data": {"Count": 0, "Posts": []}})

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(variant="experienced", keywords=["前端工程师"])

    assert len(jobs) == 1
    assert jobs[0]["PostId"] == "2001"
    assert "前端工程师" in request_keywords
    assert "frontend engineer" in request_keywords


def test_collect_jobs_continues_after_single_keyword_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        keyword = request.url.params.get("keyword", "")
        if keyword == "前端工程师":
            raise httpx.ConnectTimeout("timeout")
        if keyword == "frontend engineer":
            return httpx.Response(
                200,
                json={
                    "Code": 200,
                    "Data": {
                        "Count": 1,
                        "Posts": [
                            {
                                "PostId": "2002",
                                "RecruitPostName": "Frontend Engineer",
                                "LastUpdateTime": "2026年3月10日",
                            }
                        ],
                    },
                },
            )
        return httpx.Response(200, json={"Code": 200, "Data": {"Count": 0, "Posts": []}})

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="experienced", keywords=["前端工程师"])
    assert len(jobs) == 1
    assert jobs[0]["PostId"] == "2002"


def test_collect_jobs_stops_when_count_reached():
    seen_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_pages.append(request.url.params["pageIndex"])
        page_index = int(request.url.params["pageIndex"])
        if page_index == 1:
            payload = {
                "Code": 200,
                "Data": {
                    "Count": 1,
                    "Posts": [
                        {
                            "PostId": "1001",
                            "RecruitPostName": "Frontend Engineer",
                            "LastUpdateTime": "2026年03月10日",
                        }
                    ],
                },
            }
            return httpx.Response(200, json=payload)
        raise AssertionError("should not request page 2 when count is reached")

    client = build_client(handler, max_pages=5, page_size=50)
    jobs = client.collect_jobs(variant="experienced", keywords=["frontend"])
    assert len(jobs) == 1
    assert seen_pages == ["1"]


def test_collect_jobs_handles_gb18030_json_payload():
    body = {
        "Code": 200,
        "Data": {
            "Count": 1,
            "Posts": [
                {
                    "PostId": "1002",
                    "RecruitPostName": "前端开发工程师",
                    "LastUpdateTime": "2026年03月10日",
                }
            ],
        },
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("gb18030")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=body_bytes,
        )

    client = build_client(handler, max_pages=2, page_size=50)
    jobs = client.collect_jobs(variant="experienced", keywords=["前端"])
    assert len(jobs) == 1
    assert jobs[0]["PostId"] == "1002"


def test_query_params_include_variant_attr_id_and_keyword():
    observed_params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_params.append(dict(request.url.params))
        payload = {"Code": 200, "Data": {"Count": 0, "Posts": []}}
        return httpx.Response(200, json=payload)

    client = build_client(handler, max_pages=1, page_size=10)
    client.collect_jobs(variant="campus", keywords=["frontend"])

    assert len(observed_params) == 1
    params = observed_params[0]
    assert params["attrId"] == "2,5"
    assert params["pageIndex"] == "1"
    assert params["pageSize"] == "10"
    assert params["language"] == "zh-cn"
    assert params["area"] == "cn"
    assert params["keyword"] == "frontend"
