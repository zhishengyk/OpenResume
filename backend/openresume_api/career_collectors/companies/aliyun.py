from __future__ import annotations

from ..providers.aliyun_careers import AliyunCareersClient
from .alibaba_base import BaseAlibabaCareerCollector


class AliyunCollector(BaseAlibabaCareerCollector):
    collector_key = "aliyun"
    provider_cls = AliyunCareersClient
    page_limit_setting = "official_aliyun_page_limit"
    page_size_setting = "official_aliyun_page_size"


aliyun_collector = AliyunCollector()
