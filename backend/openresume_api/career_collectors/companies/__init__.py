from .bytedance import bytedance_collector


REGISTERED_COLLECTORS = (bytedance_collector,)

__all__ = ["REGISTERED_COLLECTORS", "bytedance_collector"]
