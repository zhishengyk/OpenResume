from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import AppSetting, ApplicationAttempt, RiskEvent


class RiskControlService:
    hourly_limit = 5
    daily_limit = 20
    pause_window = timedelta(minutes=30)

    def current_status(self, db: Session, platform: str) -> dict:
        now = datetime.utcnow()
        hour_cutoff = now - timedelta(hours=1)
        day_cutoff = now - timedelta(days=1)
        hourly_attempts = db.exec(
            select(ApplicationAttempt).where(
                ApplicationAttempt.platform == platform,
                ApplicationAttempt.created_at >= hour_cutoff,
            )
        ).all()
        daily_attempts = db.exec(
            select(ApplicationAttempt).where(
                ApplicationAttempt.platform == platform,
                ApplicationAttempt.created_at >= day_cutoff,
            )
        ).all()
        recent_events = db.exec(
            select(RiskEvent).where(
                RiskEvent.platform == platform,
                RiskEvent.created_at >= now - self.pause_window,
            )
        ).all()
        pause_setting = db.get(AppSetting, f"platform_pause:{platform}")
        emergency_stop = db.get(AppSetting, "emergency_stop")
        cooldown_until = None
        if pause_setting:
            cooldown_raw = pause_setting.value.get("until")
            if cooldown_raw:
                cooldown_until = datetime.fromisoformat(cooldown_raw)

        return {
            "platform": platform,
            "emergency_stop_active": bool(emergency_stop and emergency_stop.value.get("active")),
            "cooldown_until": cooldown_until,
            "remaining_hourly": max(0, self.hourly_limit - len(hourly_attempts)),
            "remaining_daily": max(0, self.daily_limit - len(daily_attempts)),
            "recent_risk_events": len(recent_events),
        }

    def set_emergency_stop(self, db: Session, active: bool) -> dict:
        setting = db.get(AppSetting, "emergency_stop")
        if not setting:
            setting = AppSetting(key="emergency_stop", value={})
        setting.value = {"active": active}
        db.add(setting)
        db.commit()
        return {"active": active}

    def record_risk_event(self, db: Session, platform: str, event_type: str, detail: str) -> RiskEvent:
        event = RiskEvent(platform=platform, event_type=event_type, detail=detail)
        db.add(event)
        db.commit()
        db.refresh(event)

        recent = db.exec(
            select(RiskEvent).where(
                RiskEvent.platform == platform,
                RiskEvent.created_at >= datetime.utcnow() - self.pause_window,
                RiskEvent.event_type.in_(["captcha", "blocked"]),
            )
        ).all()
        if len(recent) >= 2:
            pause_setting = db.get(AppSetting, f"platform_pause:{platform}") or AppSetting(
                key=f"platform_pause:{platform}",
                value={},
            )
            pause_setting.value = {
                "until": (datetime.utcnow() + self.pause_window).isoformat(),
                "reason": "Repeated risk events",
            }
            db.add(pause_setting)
            db.commit()
        return event

    def ensure_guided_apply_allowed(self, db: Session, platform: str) -> None:
        status = self.current_status(db, platform)
        if status["emergency_stop_active"]:
            raise HTTPException(status_code=409, detail="Emergency stop is active.")
        cooldown_until = status["cooldown_until"]
        if cooldown_until and cooldown_until > datetime.utcnow():
            raise HTTPException(
                status_code=429,
                detail=f"Platform is in cooldown until {cooldown_until.isoformat()}",
            )
        if status["remaining_hourly"] <= 0:
            raise HTTPException(status_code=429, detail="Hourly guided-apply limit reached.")
        if status["remaining_daily"] <= 0:
            raise HTTPException(status_code=429, detail="Daily guided-apply limit reached.")


risk_control_service = RiskControlService()

