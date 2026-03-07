from __future__ import annotations

from datetime import datetime
from pathlib import Path
import webbrowser

from sqlmodel import Session

from ..config import settings
from ..models import AppSetting


class BrowserSessionService:
    def session_dir(self, platform: str) -> Path:
        directory = settings.browser_dir / platform
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def start(self, db: Session, platform: str, login_url: str) -> dict:
        storage_dir = self.session_dir(platform)
        if not settings.disable_browser_open:
            webbrowser.open(login_url)
        setting = AppSetting(
            key=f"platform_session:{platform}",
            value={
                "active": True,
                "last_started_at": datetime.utcnow().isoformat(),
                "storage_dir": str(storage_dir),
            },
        )
        existing = db.get(AppSetting, setting.key)
        if existing:
            existing.value = setting.value
            db.add(existing)
        else:
            db.add(setting)
        db.commit()
        return setting.value

    def state(self, db: Session, platform: str) -> dict:
        setting = db.get(AppSetting, f"platform_session:{platform}")
        storage_dir = self.session_dir(platform)
        if not setting:
            return {
                "active": False,
                "storage_dir": str(storage_dir),
                "last_started_at": None,
            }
        return {
            "active": bool(setting.value.get("active")),
            "storage_dir": str(storage_dir),
            "last_started_at": setting.value.get("last_started_at"),
        }


browser_session_service = BrowserSessionService()
