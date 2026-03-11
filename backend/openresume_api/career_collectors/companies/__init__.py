from .alibaba_holding import alibaba_holding_collector
from .aliyun import aliyun_collector
from .bytedance import bytedance_collector
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
    meituan_collector,
    pdd_collector,
)

__all__ = [
    "REGISTERED_COLLECTORS",
    "alibaba_holding_collector",
    "bytedance_collector",
    "tencent_collector",
    "taobao_collector",
    "aliyun_collector",
    "meituan_collector",
    "pdd_collector",
]
