from __future__ import annotations

from ..providers.aidc_careers import AidcCareerClient
from .alibaba_base import BaseAlibabaCareerCollector


class AidcCollector(BaseAlibabaCareerCollector):
    collector_key = "aidc"
    provider_cls = AidcCareerClient
    page_limit_setting = "official_aidc_page_limit"
    page_size_setting = "official_aidc_page_size"


aidc_collector = AidcCollector()
