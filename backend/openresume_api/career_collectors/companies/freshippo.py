from __future__ import annotations

from ..providers.freshippo_careers import FreshippoCareerClient
from .alibaba_base import BaseAlibabaCareerCollector


class FreshippoCollector(BaseAlibabaCareerCollector):
    collector_key = "freshippo"
    provider_cls = FreshippoCareerClient
    page_limit_setting = "official_freshippo_page_limit"
    page_size_setting = "official_freshippo_page_size"


freshippo_collector = FreshippoCollector()
