from __future__ import annotations

import json
from pathlib import Path

from ..config import settings

try:
    import keyring  # type: ignore
except ImportError:  # pragma: no cover - optional runtime dependency
    keyring = None


class CredentialStore:
    def __init__(self) -> None:
        self._service_name = "openresume-official"
        self._fallback_path = settings.storage_dir / "credentials.json"

    def has_password(self, credential_key: str) -> bool:
        return bool(self.get_password(credential_key))

    def get_password(self, credential_key: str) -> str:
        if not credential_key:
            return ""
        if keyring is not None:
            try:
                return str(
                    keyring.get_password(self._service_name, credential_key) or ""
                )
            except Exception:
                return self._read_fallback().get(credential_key, "")
        return self._read_fallback().get(credential_key, "")

    def set_password(self, credential_key: str, password: str) -> None:
        if not credential_key:
            return
        if keyring is not None:
            try:
                keyring.set_password(self._service_name, credential_key, password)
                return
            except Exception:
                pass
        payload = self._read_fallback()
        payload[credential_key] = password
        self._write_fallback(payload)

    def delete_password(self, credential_key: str) -> None:
        if not credential_key:
            return
        if keyring is not None:
            try:
                keyring.delete_password(self._service_name, credential_key)
            except Exception:
                pass
        payload = self._read_fallback()
        if credential_key in payload:
            payload.pop(credential_key, None)
            self._write_fallback(payload)

    def _read_fallback(self) -> dict[str, str]:
        if not self._fallback_path.exists():
            return {}
        try:
            raw = json.loads(self._fallback_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in raw.items()
            if str(key).strip() and isinstance(value, str)
        }

    def _write_fallback(self, payload: dict[str, str]) -> None:
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        self._fallback_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


credential_store = CredentialStore()
