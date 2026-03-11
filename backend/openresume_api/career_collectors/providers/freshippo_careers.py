from __future__ import annotations

import httpx

from .alibaba_careers import (
    AlibabaCareerClient,
    AlibabaCareerSiteConfig,
    AlibabaCareerVariantConfig,
)


BASE_URL = "https://hire.freshippo.com"

VARIANT_CONFIGS: dict[str, AlibabaCareerVariantConfig] = {
    "experienced": AlibabaCareerVariantConfig(
        variant="experienced",
        entry_url="https://hire.freshippo.com/home?lang=zh",
        channel="hema_group_official_site",
        category_type=None,
        detail_path_template=(
            "https://hire.freshippo.com/off-campus/position-detail?positionId={job_id}"
        ),
    ),
    "campus": AlibabaCareerVariantConfig(
        variant="campus",
        entry_url="https://hire.freshippo.com/campus/home?lang=zh",
        channel="hema_campus_group_official_site",
        category_type="freshman",
        detail_path_template=(
            "https://hire.freshippo.com/campus/position-detail?positionId={job_id}"
        ),
    ),
    "internship": AlibabaCareerVariantConfig(
        variant="internship",
        entry_url="https://hire.freshippo.com/campus/home?lang=zh",
        channel="hema_campus_group_official_site",
        category_type="internship",
        detail_path_template=(
            "https://hire.freshippo.com/campus/position-detail?positionId={job_id}"
        ),
    ),
}

SITE_CONFIG = AlibabaCareerSiteConfig(
    base_url=BASE_URL,
    variants=VARIANT_CONFIGS,
)


class FreshippoCareerClient(AlibabaCareerClient):
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
