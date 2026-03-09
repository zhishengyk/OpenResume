from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import urlparse

from ..config import settings


@dataclass(frozen=True)
class OfficialSource:
    company_name: str
    url: str
    host: str
    source_kind: str


def _classify_source(url: str) -> str:
    lowered = url.lower()
    if "mokahr.com" in lowered:
        return "moka"
    if "feishu.cn" in lowered:
        return "feishu"
    if "hotjob.cn" in lowered or "zhiye.com" in lowered:
        return "hotjob"
    if any(token in lowered for token in ["campus", "career", "careers", "jobs"]):
        return "career_site"
    return "official_site"


def _parse_line(line: str) -> tuple[str, str] | None:
    if "http://" not in line and "https://" not in line:
        return None
    match = re.search(r"https?://\S+", line)
    if not match:
        return None
    url = match.group(0).strip().rstrip(")")
    prefix = line[: match.start()].strip().rstrip(":：")
    company_name = re.sub(r"\s+", " ", prefix).strip()
    if not company_name:
        company_name = urlparse(url).netloc
    return company_name, url


def _load_sources_from_file(path: Path) -> list[OfficialSource]:
    if not path.exists():
        return []

    seen_urls: set[str] = set()
    sources: list[OfficialSource] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parsed = _parse_line(raw_line)
        if not parsed:
            continue
        company_name, url = parsed
        host = urlparse(url).netloc.lower().lstrip("www.")
        if not host:
            continue
        dedupe_key = url.lower().rstrip("/")
        if dedupe_key in seen_urls:
            continue
        seen_urls.add(dedupe_key)
        sources.append(
            OfficialSource(
                company_name=company_name,
                url=url,
                host=host,
                source_kind=_classify_source(url),
            )
        )
    return sources


class OfficialSourceService:
    @lru_cache(maxsize=1)
    def load_sources(self) -> tuple[OfficialSource, ...]:
        return tuple(_load_sources_from_file(settings.official_source_file))

    def clear_cache(self) -> None:
        self.load_sources.cache_clear()


official_source_service = OfficialSourceService()
