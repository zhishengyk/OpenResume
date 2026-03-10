from __future__ import annotations

from datetime import UTC, datetime
import html
import re


COMMON_CITY_ALIASES = {
    "beijing": "北京",
    "shanghai": "上海",
    "hangzhou": "杭州",
    "shenzhen": "深圳",
    "guangzhou": "广州",
    "suzhou": "苏州",
    "chengdu": "成都",
}


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u3000", " ")).strip()


def normalize_multiline_text(value: str) -> str:
    cleaned_lines = [line.strip() for line in (value or "").splitlines()]
    return "\n".join(line for line in cleaned_lines if line)


def normalize_city(value: str) -> str:
    city = normalize_whitespace(value)
    if not city:
        return ""
    lowered = city.lower()
    if lowered in COMMON_CITY_ALIASES:
        return COMMON_CITY_ALIASES[lowered]
    city = re.split(r"\s*[·・•/_|,，(（]\s*|\s+-\s+", city, maxsplit=1)[0].strip()
    if city.endswith("市"):
        city = city[:-1]
    return city


def build_description_html(description: str, requirements: str) -> str:
    sections: list[str] = []
    if description:
        sections.append(
            "<section><h2>职位描述</h2>{}</section>".format(
                _paragraphs_to_html(description)
            )
        )
    if requirements:
        sections.append(
            "<section><h2>任职要求</h2>{}</section>".format(
                _paragraphs_to_html(requirements)
            )
        )
    return "".join(sections)


def epoch_millis_to_datetime(value: int | float | str | None) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(numeric / 1000, UTC).replace(tzinfo=None)


def _paragraphs_to_html(value: str) -> str:
    parts = []
    for paragraph in normalize_multiline_text(value).splitlines():
        parts.append(f"<p>{html.escape(paragraph)}</p>")
    return "".join(parts)
