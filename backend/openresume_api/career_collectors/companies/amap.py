from __future__ import annotations

from ..providers.amap_careers import AmapCareerClient
from .alibaba_base import BaseAlibabaCareerCollector


class AmapCollector(BaseAlibabaCareerCollector):
    collector_key = "amap"
    provider_cls = AmapCareerClient
    page_limit_setting = "official_amap_page_limit"
    page_size_setting = "official_amap_page_size"


amap_collector = AmapCollector()
