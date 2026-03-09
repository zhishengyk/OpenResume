import asyncio

import httpx

from openresume_api.adapters.official_extractors.base import FetchPage
from openresume_api.adapters.official_extractors.bytedance import BytedanceExtractor
from openresume_api.adapters.official_extractors.feishu import FeishuExtractor
from openresume_api.adapters.official_extractors.generic import GenericExtractor
from openresume_api.adapters.official_extractors.hotjob import HotjobExtractor
from openresume_api.adapters.official_extractors.json_ssr import JsonSsrExtractor
from openresume_api.adapters.official_extractors.moka import MokaExtractor
from openresume_api.adapters.official_extractors.pdd import PddExtractor
from openresume_api.adapters.official_extractors.taobao import TaobaoExtractor
from openresume_api.services.official_sources import OfficialSource


def make_source(
    url: str,
    *,
    source_kind: str = "official_site",
    company_name: str = "Example Corp",
) -> OfficialSource:
    return OfficialSource(
        company_name=company_name,
        url=url,
        host=httpx.URL(url).host or "example.com",
        source_kind=source_kind,
    )


def make_page(
    url: str,
    text: str,
    *,
    content_type: str = "text/html",
) -> FetchPage:
    return FetchPage(
        requested_url=url,
        final_url=url,
        text=text,
        status_code=200,
        content_type=content_type,
    )


def test_generic_extractor_extracts_anchor_candidates():
    extractor = GenericExtractor()
    source = make_source("https://careers.example.com")
    page = make_page(
        "https://careers.example.com",
        """
        <html>
          <body>
            <a href="/jobs/frontend">Senior Frontend Engineer - Shanghai</a>
            <a href="/faq">FAQ</a>
          </body>
        </html>
        """,
    )

    candidates = extractor.extract_candidates(
        source=source,
        page=page,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
    )

    assert len(candidates) == 1
    assert candidates[0].title == "Senior Frontend Engineer - Shanghai"
    assert candidates[0].detail_url == "https://careers.example.com/jobs/frontend"
    assert candidates[0].city == "Shanghai"
    assert candidates[0].raw_payload["source"] == "anchor"


def test_json_ssr_extractor_reads_next_data_payload():
    extractor = JsonSsrExtractor()
    source = make_source("https://careers.example.com")
    page = make_page(
        "https://careers.example.com",
        """
        <script id="__NEXT_DATA__" type="application/json">
          {
            "props": {
              "pageProps": {
                "jobs": [
                  {
                    "title": "Senior Frontend Engineer",
                    "detailUrl": "/jobs/next-1",
                    "location": "Shanghai",
                    "department": "Platform",
                    "description": "React TypeScript 15K-25K"
                  }
                ]
              }
            }
          }
        </script>
        """,
    )

    candidates = extractor.extract_candidates(
        source=source,
        page=page,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
    )

    assert len(candidates) == 1
    assert candidates[0].detail_url == "https://careers.example.com/jobs/next-1"
    assert candidates[0].city == "Shanghai"
    assert candidates[0].department == "Platform"
    assert candidates[0].salary_min == 15000


def test_feishu_extractor_reads_embedded_payload_and_detail_sections():
    extractor = FeishuExtractor()
    source = make_source("https://jobs.example.com", source_kind="feishu")
    list_page = make_page(
        "https://jobs.example.com",
        """
        <script id="js-websiteInfo" type="application/json">
          {
            "jobs": [
              {
                "title": "Senior Frontend Engineer",
                "website_path": "/position/123/detail",
                "city": "Shanghai",
                "department": "Platform",
                "description": "React TypeScript 20K-30K"
              }
            ]
          }
        </script>
        """,
    )

    candidates = extractor.extract_candidates(
        source=source,
        page=list_page,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
    )

    detail_page = make_page(
        "https://jobs.example.com/position/123/detail",
        """
        <html>
          <body>
            <h1>Senior Frontend Engineer</h1>
            <p>Responsibilities Build React hiring tools and frontend systems.</p>
            <p>Requirements Strong TypeScript and testing experience.</p>
            <p>Location Shanghai</p>
            <p>Department Platform</p>
          </body>
        </html>
        """,
    )
    detail = extractor.extract_detail(
        source=source,
        candidate=candidates[0],
        page=detail_page,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
    )

    assert extractor.matches(source, list_page) is True
    assert len(candidates) == 1
    assert candidates[0].detail_url == "https://jobs.example.com/position/123/detail"
    assert detail.classification == "job_detail"
    assert detail.responsibilities.startswith("Build React")
    assert detail.requirements.startswith("Strong TypeScript")
    assert detail.location_text == "Shanghai"
    assert detail.department == "Platform"


def test_moka_extractor_reads_initial_state_payload():
    extractor = MokaExtractor()
    source = make_source("https://example.mokahr.com/jobs", source_kind="moka")
    page = make_page(
        "https://example.mokahr.com/jobs",
        """
        <script>
          window.__INITIAL_STATE__ = {
            "jobs": [
              {
                "positionName": "Senior Frontend Engineer",
                "jobUrl": "/jobs/moka-1",
                "location": "Shanghai",
                "department": "Platform",
                "description": "React TypeScript 18K-28K Bachelor"
              }
            ]
          };
        </script>
        """,
    )

    candidates = extractor.extract_candidates(
        source=source,
        page=page,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
    )

    assert extractor.matches(source, page) is True
    assert len(candidates) == 1
    assert candidates[0].detail_url == "https://example.mokahr.com/jobs/moka-1"
    assert candidates[0].city == "Shanghai"
    assert candidates[0].degree_text == "Bachelor"


def test_hotjob_extractor_resolves_shell_page_before_extraction():
    extractor = HotjobExtractor()
    source = make_source("https://jobs.example.com/campus", source_kind="hotjob")
    shell_page = make_page(
        "https://jobs.example.com/campus",
        "<html><body>wecruit/common/getSLD</body></html>",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and str(request.url).endswith("/wecruit/common/getSLD"):
            return httpx.Response(
                200,
                json={"data": {"linkData": {"wtLink": "https://landing.example.com/jobs"}}},
            )
        if request.method == "GET" and str(request.url) == "https://landing.example.com/jobs":
            return httpx.Response(
                200,
                text="<html><body>landing page</body></html>",
                headers={"content-type": "text/html"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def run_test() -> FetchPage:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await extractor.prepare_source_page(client, source, shell_page)

    prepared = asyncio.run(run_test())

    assert extractor.matches(source, shell_page) is True
    assert prepared.final_url == "https://landing.example.com/jobs"
    assert "landing page" in prepared.text


def test_bytedance_extractor_follows_homepage_to_position_page():
    extractor = BytedanceExtractor()
    source = make_source("https://jobs.bytedance.com/", source_kind="bytedance", company_name="字节跳动")
    homepage = make_page(
        "https://jobs.bytedance.com/",
        """
        <html>
          <body>
            <a href="/campus">校园招聘</a>
          </body>
        </html>
        """,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and url == "https://jobs.bytedance.com/campus":
            return httpx.Response(
                200,
                text="""
                <html>
                  <body>
                    <a href="/campus/position">职位列表</a>
                  </body>
                </html>
                """,
                headers={"content-type": "text/html"},
            )
        if request.method == "GET" and url == "https://jobs.bytedance.com/campus/position":
            return httpx.Response(
                200,
                text="""
                <script id="js-websiteInfo" type="application/json">
                  {
                    "jobs": [
                      {
                        "title": "前端开发工程师",
                        "website_path": "/campus/position/1950/detail",
                        "city": "Shanghai",
                        "department": "ByteDance Infra",
                        "description": "岗位职责 负责招聘前端系统建设 任职要求 熟悉 React TypeScript"
                      }
                    ]
                  }
                </script>
                """,
                headers={"content-type": "text/html"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def run_test() -> FetchPage:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await extractor.prepare_source_page(client, source, homepage)

    prepared = asyncio.run(run_test())
    candidates = extractor.extract_candidates(
        source=source,
        page=prepared,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
    )

    detail_page = make_page(
        "https://jobs.bytedance.com/campus/position/1950/detail",
        """
        <html>
          <body>
            <h1>前端开发工程师</h1>
            <p>岗位职责 负责招聘前端系统建设与体验优化。</p>
            <p>任职要求 熟悉 React TypeScript 与工程化。</p>
            <p>工作地点 Shanghai</p>
          </body>
        </html>
        """,
    )
    detail = extractor.extract_detail(
        source=source,
        candidate=candidates[0],
        page=detail_page,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Shanghai"],
    )

    assert len(candidates) == 1
    assert candidates[0].detail_url == "https://jobs.bytedance.com/campus/position/1950/detail"
    assert candidates[0].department == "ByteDance Infra"
    assert detail.classification == "job_detail"
    assert detail.location_text == "Shanghai"


def test_bytedance_extractor_prefers_canonical_position_page_before_share_queries(monkeypatch):
    extractor = BytedanceExtractor()
    source = make_source("https://jobs.bytedance.com/", source_kind="bytedance", company_name="ByteDance")
    homepage = make_page(
        "https://jobs.bytedance.com/",
        """
        <html>
          <body>
            <a href="/campus">campus</a>
            <a href="/campus/position?keywords=nohits">share query</a>
          </body>
        </html>
        """,
    )

    seen_position_pages: list[str] = []

    async def fake_api_position_pages(client, page):
        seen_position_pages.append(page.final_url)
        if page.final_url == "https://jobs.bytedance.com/campus/position":
            return [
                make_page(
                    "https://jobs.bytedance.com/api/v1/search/job/posts",
                    """
                    {"data":{"job_post_list":[
                      {
                        "id":"1950",
                        "title":"Backend Engineer",
                        "description":"Build hiring systems",
                        "city_info":"Shanghai",
                        "department_info":"Infra"
                      }
                    ]}}
                    """,
                    content_type="application/json",
                )
            ]
        return []

    monkeypatch.setattr(extractor, "_api_position_pages", fake_api_position_pages)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and url == "https://jobs.bytedance.com/campus":
            return httpx.Response(
                200,
                text='<html><body><a href="/campus/position">positions</a></body></html>',
                headers={"content-type": "text/html"},
            )
        if request.method == "GET" and url == "https://jobs.bytedance.com/campus/position":
            return httpx.Response(
                200,
                text="<html><body>canonical list</body></html>",
                headers={"content-type": "text/html"},
            )
        if request.method == "GET" and url == "https://jobs.bytedance.com/campus/position?keywords=nohits":
            return httpx.Response(
                200,
                text="<html><body>share query</body></html>",
                headers={"content-type": "text/html"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def run_test() -> FetchPage:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await extractor.prepare_source_page(client, source, homepage)

    prepared = asyncio.run(run_test())
    candidates = extractor.extract_candidates(
        source=source,
        page=prepared,
        requested_targets=["Backend Engineer"],
        requested_cities=["Shanghai"],
    )

    assert seen_position_pages == ["https://jobs.bytedance.com/campus/position"]
    assert len(candidates) == 1
    assert candidates[0].detail_url == "https://jobs.bytedance.com/campus/position/1950/detail"
    assert candidates[0].raw_payload["api_source"] == "bytedance-api"


def test_taobao_extractor_uses_position_api_and_payload_detail_fallback():
    extractor = TaobaoExtractor()
    source = make_source("https://zhaopin.taobao.com/", source_kind="taobao", company_name="淘宝")
    homepage = make_page(
        "https://zhaopin.taobao.com/",
        """
        <html>
          <body>
            <a href="https://talent.taotian.com/campus/position-list?campusType=freshman&lang=zh">
              校招职位
            </a>
          </body>
        </html>
        """,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and url == (
            "https://talent.taotian.com/campus/position-list?campusType=freshman&lang=zh"
        ):
            return httpx.Response(
                200,
                text="""
                <html>
                  <body>
                    <script>
                      window.__sysconfig = {
                        __token__: "mock-token"
                      };
                    </script>
                  </body>
                </html>
                """,
                headers={"content-type": "text/html"},
            )
        if request.method == "GET" and url == (
            "https://talent.taotian.com/campus/position-list?campusType=internship&lang=zh"
        ):
            return httpx.Response(
                200,
                text="""
                <html>
                  <body>
                    <script>
                      window.__sysconfig = {
                        __token__: "mock-token"
                      };
                    </script>
                  </body>
                </html>
                """,
                headers={"content-type": "text/html"},
            )
        if request.method == "POST" and url == (
            "https://talent.taotian.com/searchCondition/list?_csrf=mock-token"
        ):
            return httpx.Response(
                200,
                json={"success": True, "content": {"searchItems": [], "totalPositions": 1}},
            )
        if request.method == "POST" and url == "https://talent.taotian.com/position/search?_csrf=mock-token":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "content": {
                        "totalCount": 1,
                        "datas": [
                                {
                                    "name": "淘宝前端开发工程师",
                                    "id": 2020815,
                                    "workLocations": ["Hangzhou"],
                                    "department": "淘宝技术",
                                    "description": (
                                        "岗位职责 负责淘宝前端架构与工程化建设，推动核心业务体验优化，"
                                        "参与复杂前端系统设计与稳定性治理。"
                                    ),
                                    "requirement": (
                                        "任职要求 熟悉 React TypeScript，具备复杂前端系统经验，"
                                        "理解工程化、性能优化和测试体系。"
                                    ),
                                }
                            ]
                        }
                    },
                )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def run_test() -> FetchPage:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await extractor.prepare_source_page(client, source, homepage)

    prepared = asyncio.run(run_test())
    candidates = extractor.extract_candidates(
        source=source,
        page=prepared,
        requested_targets=["Frontend Engineer"],
        requested_cities=["Hangzhou"],
    )
    detail = extractor.extract_detail(
        source=source,
        candidate=candidates[0],
        page=make_page(
            "https://talent.taotian.com/campus/position-detail?lang=zh&positionId=2020815",
            "<html><body><div id='root'></div></body></html>",
        ),
        requested_targets=["Frontend Engineer"],
        requested_cities=["Hangzhou"],
    )

    assert len(candidates) == 1
    assert candidates[0].detail_url.endswith("positionId=2020815")
    assert candidates[0].city == "Hangzhou"
    assert detail.classification == "job_detail"
    assert "React TypeScript" in detail.requirements
    assert detail.department == "淘宝技术"


def test_pdd_extractor_follows_grad_page_position_api_and_detail_api():
    extractor = PddExtractor()
    source = make_source(
        "https://careers.pddglobalhr.com/campus",
        source_kind="pdd",
        company_name="拼多多",
    )
    homepage = make_page(
        "https://careers.pddglobalhr.com/campus",
        """
        <html>
          <body>
            <a href="/campus/grad">校招</a>
            <a href="/campus/intern">实习</a>
          </body>
        </html>
        """,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and url == "https://careers.pddglobalhr.com/campus/grad":
            return httpx.Response(
                200,
                text="""
                <html>
                  <body>
                    <div id="root">grad shell</div>
                  </body>
                </html>
                """,
                headers={"content-type": "text/html"},
            )
        if request.method == "GET" and url == "https://careers.pddglobalhr.com/campus/intern":
            return httpx.Response(
                200,
                text="<html><body>intern shell</body></html>",
                headers={"content-type": "text/html"},
            )
        if request.method == "POST" and url == (
            "https://careers.pddglobalhr.com/api/careers/api/recruit/position/list"
        ):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "total": 1,
                        "list": [
                            {
                                "id": "grad-position-1",
                                "name": "服务端研发工程师",
                                "workLocationName": "Shanghai",
                                "jobName": "技术平台",
                                "jobDuty": "岗位职责 负责后端服务开发与稳定性建设",
                                "serveRequirement": "任职要求 熟悉 Go Java 微服务",
                            }
                        ]
                    }
                },
            )
        if request.method == "POST" and url == (
            "https://careers.pddglobalhr.com/api/careers/api/recruit/position/train/list"
        ):
            return httpx.Response(
                200,
                json={"success": True, "result": {"total": 0, "list": []}},
            )
        if request.method == "POST" and url == (
            "https://careers.pddglobalhr.com/api/careers/api/recruit/position/detail"
        ):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "id": "grad-position-1",
                        "name": "服务端研发工程师",
                        "workLocationName": "Shanghai",
                        "jobName": "技术平台",
                        "jobDuty": "岗位职责 负责后端服务开发与稳定性建设",
                        "serveRequirement": "任职要求 熟悉 Go Java 微服务",
                        "normal": True,
                    }
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def run_source_test() -> FetchPage:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await extractor.prepare_source_page(client, source, homepage)

    prepared = asyncio.run(run_source_test())
    candidates = extractor.extract_candidates(
        source=source,
        page=prepared,
        requested_targets=["Backend Engineer"],
        requested_cities=["Shanghai"],
    )

    detail_shell = make_page(
        "https://careers.pddglobalhr.com/campus/grad/detail?positionId=grad-position-1",
        """
        <html>
          <body>
            <div id="root">detail shell</div>
          </body>
        </html>
        """,
    )

    async def run_detail_test() -> FetchPage:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await extractor.prepare_detail_page(client, source, candidates[0], detail_shell)

    prepared_detail = asyncio.run(run_detail_test())
    detail = extractor.extract_detail(
        source=source,
        candidate=candidates[0],
        page=prepared_detail,
        requested_targets=["Backend Engineer"],
        requested_cities=["Shanghai"],
    )

    assert len(candidates) == 1
    assert candidates[0].detail_url.endswith("/campus/grad/detail?positionId=grad-position-1")
    assert candidates[0].city == "Shanghai"
    assert detail.classification == "job_detail"
    assert "Go Java" in detail.requirements
    assert detail.department == "技术平台"
