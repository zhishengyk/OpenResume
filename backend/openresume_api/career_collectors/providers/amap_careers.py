from __future__ import annotations

import httpx

from .alibaba_careers import (
    AlibabaCareerClient,
    AlibabaCareerSiteConfig,
    AlibabaCareerVariantConfig,
)


BASE_URL = "https://talent.amap.com"

VARIANT_CONFIGS: dict[str, AlibabaCareerVariantConfig] = {
    "experienced": AlibabaCareerVariantConfig(
        variant="experienced",
        entry_url="https://talent.amap.com/off-campus/position-list?lang=zh",
        channel="group_official_site",
        category_type=None,
        detail_path_template=(
            "https://talent.amap.com/off-campus/position-detail?positionId={job_id}"
        ),
        search_keyword_field="key",
        search_extra_payload={
            "batchId": "",
            "categories": "",
            "deptCodes": [],
            "regions": "",
            "subCategories": "",
            "shareType": "",
            "shareId": "",
            "myReferralShareCode": "",
        },
    ),
    "campus": AlibabaCareerVariantConfig(
        variant="campus",
        entry_url=(
            "https://talent.amap.com/campus/position-list?campusType=freshman&lang=zh"
        ),
        channel="campus_group_official_site",
        category_type="freshman",
        detail_path_template=(
            "https://talent.amap.com/campus/position-detail"
            "?positionId={job_id}&campusType=freshman"
        ),
        search_keyword_field="key",
        search_extra_payload={
            "batchId": "",
            "subCategories": "",
            "regions": "",
            "customDeptCode": "",
            "corpCode": "",
        },
    ),
    "internship": AlibabaCareerVariantConfig(
        variant="internship",
        entry_url=(
            "https://talent.amap.com/campus/position-list?campusType=internship&lang=zh"
        ),
        channel="campus_group_official_site",
        category_type="talentPlan",
        detail_path_template=(
            "https://talent.amap.com/campus/position-detail"
            "?positionId={job_id}&campusType=internship"
        ),
        search_keyword_field="key",
        search_extra_payload={
            "batchId": "100000280001",
            "subCategories": "",
            "regions": "",
            "customDeptCode": "",
            "corpCode": "",
        },
    ),
}

SITE_CONFIG = AlibabaCareerSiteConfig(
    base_url=BASE_URL,
    variants=VARIANT_CONFIGS,
)


class AmapCareerClient(AlibabaCareerClient):
    def __init__(
        self,
        *,
        timeout_seconds: float,
        user_agent: str,
        max_pages: int,
        page_size: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            site_config=SITE_CONFIG,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            max_pages=max_pages,
            page_size=page_size,
            transport=transport,
        )
