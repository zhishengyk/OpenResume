from __future__ import annotations

from .boss import boss_adapter
from .official import official_adapter


REGISTERED_ADAPTERS = (
    official_adapter,
    boss_adapter,
)
