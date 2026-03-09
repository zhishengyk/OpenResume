from __future__ import annotations

from .base import DetailExtraction, ExtractedCandidate, FetchPage, OfficialExtractor
from .bytedance import BytedanceExtractor
from .feishu import FeishuExtractor
from .generic import GenericExtractor
from .hotjob import HotjobExtractor
from .json_ssr import JsonSsrExtractor
from .moka import MokaExtractor
from .pdd import PddExtractor
from .taobao import TaobaoExtractor

EXTRACTOR_REGISTRY: tuple[OfficialExtractor, ...] = (
    BytedanceExtractor(),
    TaobaoExtractor(),
    PddExtractor(),
    FeishuExtractor(),
    MokaExtractor(),
    HotjobExtractor(),
    JsonSsrExtractor(),
    GenericExtractor(),
)

__all__ = [
    "DetailExtraction",
    "EXTRACTOR_REGISTRY",
    "ExtractedCandidate",
    "FetchPage",
    "OfficialExtractor",
]
