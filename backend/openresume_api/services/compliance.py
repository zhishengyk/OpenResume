from __future__ import annotations

from sqlmodel import Session, select

from ..models import AppSetting, RiskConsent


class ComplianceService:
    def app_state(self, db: Session) -> dict:
        launch_disclaimer = db.exec(
            select(RiskConsent).where(RiskConsent.consent_type == "launch_disclaimer")
        ).first()
        guided_consents = db.exec(
            select(RiskConsent).where(RiskConsent.consent_type == "guided_apply")
        ).all()
        emergency_setting = db.get(AppSetting, "emergency_stop")

        return {
            "launch_disclaimer_required": launch_disclaimer is None,
            "guided_apply_consents": [consent.platform for consent in guided_consents if consent.platform],
            "emergency_stop_active": bool(emergency_setting and emergency_setting.value.get("active")),
        }

    def record_consent(
        self,
        db: Session,
        consent_type: str,
        platform: str | None,
        version: str,
    ) -> RiskConsent:
        existing = db.exec(
            select(RiskConsent).where(
                RiskConsent.consent_type == consent_type,
                RiskConsent.platform == platform,
            )
        ).first()
        if existing:
            return existing

        consent = RiskConsent(
            consent_type=consent_type,
            platform=platform,
            version=version,
        )
        db.add(consent)
        db.commit()
        db.refresh(consent)
        return consent

    def has_guided_apply_consent(self, db: Session, platform: str) -> bool:
        return (
            db.exec(
                select(RiskConsent).where(
                    RiskConsent.consent_type == "guided_apply",
                    RiskConsent.platform == platform,
                )
            ).first()
            is not None
        )


compliance_service = ComplianceService()

