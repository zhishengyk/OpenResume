from __future__ import annotations

from fastapi import HTTPException

from ..adapters.registry import REGISTERED_ADAPTERS


class PlatformGateway:
    def __init__(self) -> None:
        self.adapters = {adapter.platform: adapter for adapter in REGISTERED_ADAPTERS}

    def list_capabilities(self):
        return [adapter.capability() for adapter in self.adapters.values()]

    def get(self, platform: str):
        adapter = self.adapters.get(platform)
        if not adapter:
            raise HTTPException(status_code=404, detail=f"Unsupported platform: {platform}")
        return adapter

    def resolve(self, platforms: list[str]):
        seen: set[str] = set()
        resolved = []
        for platform in platforms:
            if platform in seen:
                continue
            resolved.append(self.get(platform))
            seen.add(platform)
        return resolved


platform_gateway = PlatformGateway()
