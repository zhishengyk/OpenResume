from __future__ import annotations

import json
from pathlib import Path

from ..config import ROOT_DIR, settings


class RulePackService:
    def __init__(self) -> None:
        self.embedded_dir = ROOT_DIR / "openresume_api" / "rules"

    def load_rule_pack(self, platform: str) -> dict:
        override_path = settings.rules_dir / f"{platform}.json"
        if override_path.exists():
            return json.loads(override_path.read_text(encoding="utf-8"))

        default_path = self.embedded_dir / f"{platform}.default.json"
        return json.loads(default_path.read_text(encoding="utf-8"))

    def current_version(self, platform: str) -> str:
        return self.load_rule_pack(platform)["version"]


rule_pack_service = RulePackService()

