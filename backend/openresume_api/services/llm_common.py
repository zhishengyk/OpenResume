from __future__ import annotations


def _normalize_message_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
                continue
            if not isinstance(item, dict):
                continue
            for key in ("text", "content"):
                nested = item.get(key)
                if isinstance(nested, str) and nested.strip():
                    parts.append(nested.strip())
                    break
                if isinstance(nested, dict):
                    nested_text = nested.get("value") or nested.get("text")
                    if isinstance(nested_text, str) and nested_text.strip():
                        parts.append(nested_text.strip())
                        break
        return "\n".join(parts).strip()
    return str(value).strip()


def extract_chat_message_text(message: dict | None) -> str:
    normalized_message = message or {}
    primary = _normalize_message_text(normalized_message.get("content"))
    if primary:
        return primary
    reasoning = _normalize_message_text(normalized_message.get("reasoning_content"))
    if reasoning:
        return reasoning
    tool_calls = normalized_message.get("tool_calls")
    if isinstance(tool_calls, list):
        parts: list[str] = []
        for item in tool_calls:
            if not isinstance(item, dict):
                continue
            function = item.get("function")
            if not isinstance(function, dict):
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, str) and arguments.strip():
                parts.append(arguments.strip())
        if parts:
            return "\n".join(parts).strip()
    return ""
