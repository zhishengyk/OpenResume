from __future__ import annotations

from ..providers.eleme_careers import ElemeCareerClient
from .alibaba_base import BaseAlibabaCareerCollector


class ElemeCollector(BaseAlibabaCareerCollector):
    collector_key = "eleme"
    provider_cls = ElemeCareerClient
    page_limit_setting = "official_eleme_page_limit"
    page_size_setting = "official_eleme_page_size"


eleme_collector = ElemeCollector()
