from .aidc import aidc_collector
from .baidu import baidu_collector
from .alibaba_holding import alibaba_holding_collector
from .amap import amap_collector
from .ant import ant_collector
from .aliyun import aliyun_collector
from .bilibili import bilibili_collector
from .bytedance import bytedance_collector
from .dewu import dewu_collector
from .ctrip import ctrip_collector
from .didi import didi_collector
from .eleme import eleme_collector
from .freshippo import freshippo_collector
from .jd import jd_collector
from .kuaishou import kuaishou_collector
from .meituan import meituan_collector
from .mihoyo import mihoyo_collector
from .netease import netease_collector
from .pdd import pdd_collector
from .quark import quark_collector
from .tme import tme_collector
from .taobao import taobao_collector
from .tencent import tencent_collector
from .xiaohongshu import xiaohongshu_collector


REGISTERED_COLLECTORS = (
    bytedance_collector,
    tencent_collector,
    tme_collector,
    baidu_collector,
    didi_collector,
    ctrip_collector,
    netease_collector,
    quark_collector,
    taobao_collector,
    aliyun_collector,
    alibaba_holding_collector,
    amap_collector,
    eleme_collector,
    aidc_collector,
    ant_collector,
    xiaohongshu_collector,
    bilibili_collector,
    dewu_collector,
    freshippo_collector,
    mihoyo_collector,
    jd_collector,
    kuaishou_collector,
    meituan_collector,
    pdd_collector,
)

__all__ = [
    "aidc_collector",
    "REGISTERED_COLLECTORS",
    "baidu_collector",
    "alibaba_holding_collector",
    "amap_collector",
    "ant_collector",
    "bilibili_collector",
    "bytedance_collector",
    "dewu_collector",
    "ctrip_collector",
    "didi_collector",
    "eleme_collector",
    "freshippo_collector",
    "jd_collector",
    "kuaishou_collector",
    "netease_collector",
    "quark_collector",
    "tme_collector",
    "tencent_collector",
    "taobao_collector",
    "aliyun_collector",
    "meituan_collector",
    "mihoyo_collector",
    "pdd_collector",
    "xiaohongshu_collector",
]
