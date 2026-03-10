from .bytedance import bytedance_collector
from .taobao import taobao_collector
from .tencent import tencent_collector


REGISTERED_COLLECTORS = (bytedance_collector, tencent_collector, taobao_collector)

__all__ = [
    "REGISTERED_COLLECTORS",
    "bytedance_collector",
    "tencent_collector",
    "taobao_collector",
]
