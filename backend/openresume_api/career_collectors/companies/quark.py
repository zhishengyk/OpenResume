from __future__ import annotations

from ..providers.quark_careers import QuarkCareerClient
from .alibaba_base import BaseAlibabaCareerCollector


class QuarkCollector(BaseAlibabaCareerCollector):
    collector_key = "quark"
    provider_cls = QuarkCareerClient
    page_limit_setting = "official_quark_page_limit"
    page_size_setting = "official_quark_page_size"


quark_collector = QuarkCollector()
