from .aliyun import aliyun_collector
from .bytedance import bytedance_collector
from .taobao import taobao_collector
from .tencent import tencent_collector


REGISTERED_COLLECTORS = (
    bytedance_collector,
    tencent_collector,
    taobao_collector,
    aliyun_collector,
)

__all__ = [
    "REGISTERED_COLLECTORS",
    "bytedance_collector",
    "tencent_collector",
    "taobao_collector",
    "aliyun_collector",
]
