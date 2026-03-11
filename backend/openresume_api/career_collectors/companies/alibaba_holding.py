from __future__ import annotations

from ..providers.alibaba_holding import AlibabaHoldingCareerClient
from .alibaba_base import BaseAlibabaCareerCollector


class AlibabaHoldingCollector(BaseAlibabaCareerCollector):
    collector_key = "alibaba_holding"
    provider_cls = AlibabaHoldingCareerClient
    page_limit_setting = "official_alibaba_holding_page_limit"
    page_size_setting = "official_alibaba_holding_page_size"


alibaba_holding_collector = AlibabaHoldingCollector()
