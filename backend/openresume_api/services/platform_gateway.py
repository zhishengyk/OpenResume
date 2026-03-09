from __future__ import annotations

from fastapi import HTTPException

from ..adapters.registry import REGISTERED_ADAPTERS


class PlatformGateway:
    def __init__(self) -> None:
        self.adapters = {
            adapter.platform: adapter
            for adapter in REGISTERED_ADAPTERS
        }

    def list_capabilities(self):
        return [adapter.capability() for adapter in self.adapters.values()]

    def get(self, platform: str):
        adapter = self.adapters.get(platform)
        if not adapter:
            raise HTTPException(status_code=404, detail=f"不支持的平台：{platform}")
        return adapter


platform_gateway = PlatformGateway()
