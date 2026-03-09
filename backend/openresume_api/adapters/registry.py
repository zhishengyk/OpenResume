from __future__ import annotations

from .demo import demo_adapter
from .liepin import liepin_adapter


REGISTERED_ADAPTERS = (
    demo_adapter,
    liepin_adapter,
)
