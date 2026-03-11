import json

import httpx

from openresume_api.career_collectors.providers.pdd_campus import PddCampusClient


def build_client(handler, *, max_pages: int = 5, page_size: int = 50):
    transport = httpx.MockTransport(handler)
    return PddCampusClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=max_pages,
        page_size=page_size,
        transport=transport,
    )


def test_collect_jobs_uses_campus_list_path_and_dedupes():
    seen_paths: list[str] = []
    seen_names: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/api/careers/api/recruit/position/list":
            payload = json.loads(request.content.decode("utf-8"))
            seen_names.append(payload.get("name"))
            keyword = payload.get("name", "")
            if keyword == "frontend":
                return httpx.Response(
                    200,
                    json={
                        "result": {
                            "list": [{"id": "1", "name": "Frontend A", "releaseTime": 1000}],
                            "total": "1",
                        },
                        "success": True,
                    },
                )
            if keyword == "react":
                return httpx.Response(
                    200,
                    json={
                        "result": {
                            "list": [
                                {"id": "1", "name": "Frontend A", "releaseTime": 1000},
                                {"id": "2", "name": "Frontend B", "releaseTime": 2000},
                            ],
                            "total": "2",
                        },
                        "success": True,
                    },
                )
            raise AssertionError(f"unexpected payload: {payload}")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = build_client(handler, max_pages=2, page_size=20)
    jobs = client.collect_jobs(variant="campus", keywords=["frontend", "react"])
    assert [job["id"] for job in jobs] == ["2", "1"]
    assert seen_names == ["frontend", "react"]
    assert seen_paths and all(path == "/api/careers/api/recruit/position/list" for path in seen_paths)


def test_collect_jobs_uses_internship_train_list_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/careers/api/recruit/position/train/list"
        return httpx.Response(
            200,
            json={
                "result": {
                    "list": [{"id": "1", "name": "Intern A", "releaseTime": 1000}],
                    "total": "1",
                },
                "success": True,
            },
        )

    client = build_client(handler, max_pages=1, page_size=20)
    jobs = client.collect_jobs(variant="internship", keywords=["frontend"])
    assert [job["id"] for job in jobs] == ["1"]


def test_get_job_detail_reads_result_field():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/careers/api/recruit/position/detail"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {"id": "123", "t": None}
        return httpx.Response(200, json={"result": {"id": "123", "name": "Role"}, "success": True})

    client = build_client(handler, max_pages=1, page_size=20)
    detail = client.get_job_detail(variant="campus", job_id="123")
    assert detail["id"] == "123"


def test_detail_url_uses_variant_specific_path():
    client = PddCampusClient(
        timeout_seconds=10.0,
        user_agent="TestAgent/1.0",
        max_pages=1,
        page_size=20,
    )
    assert (
        client.detail_url(variant="campus", job_id="123")
        == "https://careers.pddglobalhr.com/campus/grad/detail?positionId=123"
    )
    assert (
        client.detail_url(variant="internship", job_id="123")
        == "https://careers.pddglobalhr.com/campus/intern/detail?positionId=123"
    )
