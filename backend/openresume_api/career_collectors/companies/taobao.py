from __future__ import annotations

from ..providers.taobao_taotian import TaotianCareerClient
from .alibaba_base import BaseAlibabaCareerCollector


class TaobaoCollector(BaseAlibabaCareerCollector):
    collector_key = "taobao"
    provider_cls = TaotianCareerClient
    page_limit_setting = "official_taobao_page_limit"
    page_size_setting = "official_taobao_page_size"


taobao_collector = TaobaoCollector()
