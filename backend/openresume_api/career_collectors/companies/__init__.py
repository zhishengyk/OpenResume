from .aidc import aidc_collector
from .alibaba_holding import alibaba_holding_collector
from .amap import amap_collector
from .ant import ant_collector
from .aliyun import aliyun_collector
from .bytedance import bytedance_collector
from .eleme import eleme_collector
from .jd import jd_collector
from .kuaishou import kuaishou_collector
from .meituan import meituan_collector
from .pdd import pdd_collector
from .taobao import taobao_collector
from .tencent import tencent_collector


REGISTERED_COLLECTORS = (
    bytedance_collector,
    tencent_collector,
    taobao_collector,
    aliyun_collector,
    alibaba_holding_collector,
    amap_collector,
    eleme_collector,
    aidc_collector,
    ant_collector,
    jd_collector,
    kuaishou_collector,
    meituan_collector,
    pdd_collector,
)

__all__ = [
    "aidc_collector",
    "REGISTERED_COLLECTORS",
    "alibaba_holding_collector",
    "amap_collector",
    "ant_collector",
    "bytedance_collector",
    "eleme_collector",
    "jd_collector",
    "kuaishou_collector",
    "tencent_collector",
    "taobao_collector",
    "aliyun_collector",
    "meituan_collector",
    "pdd_collector",
]
