from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import time

import httpx

from ..config import settings
from .llm_common import extract_chat_message_text


@dataclass
class LLMRuntimeConfig:
    llm_provider: str
    openai_base_url: str | None
    openai_api_key: str | None
    openai_model: str | None


@dataclass
class LLMRuntimeState:
    effective_provider: str
    configured: bool
    missing_fields: list[str]
    notice: str


class RuntimeConfigService:
    def __init__(self) -> None:
        self.config_path = settings.storage_dir / "runtime_config.json"

    def _defaults(self) -> LLMRuntimeConfig:
        return LLMRuntimeConfig(
            llm_provider=settings.llm_provider,
            openai_base_url=settings.openai_base_url,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
        )

    def _read_raw(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_raw(self, payload: dict) -> None:
        self.config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_llm_config(self) -> LLMRuntimeConfig:
        defaults = self._defaults()
        raw = self._read_raw()
        return LLMRuntimeConfig(
            llm_provider=str(raw.get("llm_provider") or defaults.llm_provider),
            openai_base_url=raw.get("openai_base_url", defaults.openai_base_url),
            openai_api_key=raw.get("openai_api_key", defaults.openai_api_key),
            openai_model=raw.get("openai_model", defaults.openai_model),
        )

    def update_llm_config(
        self,
        *,
        llm_provider: str,
        openai_base_url: str | None,
        openai_model: str | None,
        openai_api_key: str | None,
        replace_api_key: bool,
    ) -> LLMRuntimeConfig:
        current = asdict(self.get_llm_config())
        current["llm_provider"] = llm_provider
        current["openai_base_url"] = openai_base_url or None
        current["openai_model"] = openai_model or None
        if replace_api_key:
            current["openai_api_key"] = openai_api_key or None
        self._write_raw(current)
        return self.get_llm_config()

    def merge_test_config(
        self,
        *,
        llm_provider: str,
        openai_base_url: str | None,
        openai_model: str | None,
        openai_api_key: str | None,
        use_saved_api_key: bool,
    ) -> LLMRuntimeConfig:
        current = self.get_llm_config()
        return LLMRuntimeConfig(
            llm_provider=llm_provider,
            openai_base_url=openai_base_url or current.openai_base_url,
            openai_model=openai_model or current.openai_model,
            openai_api_key=(
                current.openai_api_key
                if use_saved_api_key and not openai_api_key
                else (openai_api_key or None)
            ),
        )

    @staticmethod
    def api_key_preview(api_key: str | None) -> str | None:
        if not api_key:
            return None
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:3]}{'*' * (len(api_key) - 6)}{api_key[-3:]}"

    def llm_runtime_state(
        self,
        config: LLMRuntimeConfig | None = None,
        *,
        require_model: bool = True,
    ) -> LLMRuntimeState:
        llm_config = config or self.get_llm_config()
        missing_fields: list[str] = []
        if not llm_config.openai_base_url:
            missing_fields.append("OPENRESUME_OPENAI_BASE_URL")
        if not llm_config.openai_api_key:
            missing_fields.append("OPENRESUME_OPENAI_API_KEY")
        if require_model and not llm_config.openai_model:
            missing_fields.append("OPENRESUME_OPENAI_MODEL")

        configured = (
            llm_config.llm_provider == "openai_compatible" and not missing_fields
        )

        if configured:
            return LLMRuntimeState(
                effective_provider="openai_compatible",
                configured=True,
                missing_fields=[],
                notice="已启用 OpenAI 兼容模型排序。",
            )
        if llm_config.llm_provider == "openai_compatible":
            return LLMRuntimeState(
                effective_provider="openai_compatible",
                configured=False,
                missing_fields=missing_fields,
                notice="已选择 OpenAI 兼容模型排序，但缺少必要配置。请先补全配置后再测试。",
            )
        return LLMRuntimeState(
            effective_provider="heuristic",
            configured=False,
            missing_fields=missing_fields,
            notice="当前未启用大模型，岗位会使用规则/启发式排序。",
        )

    async def list_models(self, config: LLMRuntimeConfig) -> list[str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{config.openai_base_url.rstrip('/')}/models",
                headers={
                    "Authorization": f"Bearer {config.openai_api_key}",
                },
            )
            response.raise_for_status()
            payload = response.json()

        models = payload.get("data", [])
        model_ids = [
            str(item.get("id")).strip()
            for item in models
            if isinstance(item, dict) and item.get("id")
        ]
        return sorted({model_id for model_id in model_ids if model_id})

    async def test_connection(self, config: LLMRuntimeConfig) -> dict:
        started_at = time.perf_counter()
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{config.openai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.openai_api_key}",
                },
                json={
                    "model": config.openai_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Reply with only OK.",
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 8,
                },
            )
            response.raise_for_status()
            payload = response.json()

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        message = payload.get("choices", [{}])[0].get("message", {})
        content = extract_chat_message_text(message if isinstance(message, dict) else {})
        return {
            "latency_ms": latency_ms,
            "reply_preview": str(content).strip()[:160] or None,
        }


runtime_config_service = RuntimeConfigService()
