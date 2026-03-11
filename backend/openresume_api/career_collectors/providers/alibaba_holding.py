from __future__ import annotations

import httpx

from .alibaba_careers import (
    AlibabaCareerClient,
    AlibabaCareerSiteConfig,
    AlibabaCareerVariantConfig,
)


BASE_URL = "https://talent-holding.alibaba.com"

VARIANT_CONFIGS: dict[str, AlibabaCareerVariantConfig] = {
    "experienced": AlibabaCareerVariantConfig(
        variant="experienced",
        entry_url="https://talent-holding.alibaba.com/off-campus/position-list?lang=zh",
        channel="kgjt_group_official_site",
        category_type=None,
        detail_path_template=(
            "https://talent-holding.alibaba.com/off-campus/position-detail?positionId={job_id}"
        ),
    ),
    "campus": AlibabaCareerVariantConfig(
        variant="campus",
        entry_url=(
            "https://talent-holding.alibaba.com/campus/position-list?campusType=freshman&lang=zh"
        ),
        channel="kgjt_campus_group_official_site",
        category_type="freshman",
        detail_path_template=(
            "https://talent-holding.alibaba.com/campus/position-detail"
            "?positionId={job_id}&campusType=freshman"
        ),
    ),
    "internship": AlibabaCareerVariantConfig(
        variant="internship",
        entry_url=(
            "https://talent-holding.alibaba.com/campus/position-list?campusType=internship&lang=zh"
        ),
        channel="kgjt_campus_group_official_site",
        category_type="internship",
        detail_path_template=(
            "https://talent-holding.alibaba.com/campus/position-detail"
            "?positionId={job_id}&campusType=internship"
        ),
    ),
}

SITE_CONFIG = AlibabaCareerSiteConfig(
    base_url=BASE_URL,
    variants=VARIANT_CONFIGS,
)


class AlibabaHoldingCareerClient(AlibabaCareerClient):
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
