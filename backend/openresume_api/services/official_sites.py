from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import settings


@dataclass(frozen=True)
class OfficialSiteDescriptor:
    company_key: str
    company_name: str
    label: str
    source_sites: tuple[str, ...]
    supported_variants: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    supports_auto_submit: bool = True


OFFICIAL_SITE_DESCRIPTORS: tuple[OfficialSiteDescriptor, ...] = (
    OfficialSiteDescriptor(
        company_key="bytedance",
        company_name="\u5b57\u8282\u8df3\u52a8",
        label="\u5b57\u8282\u8df3\u52a8\u5b98\u7f51",
        source_sites=("jobs.bytedance.com",),
        supported_variants=("experienced", "campus", "internship"),
        aliases=("ByteDance",),
    ),
    OfficialSiteDescriptor(
        company_key="tencent",
        company_name="\u817e\u8baf",
        label="\u817e\u8baf\u5b98\u7f51",
        source_sites=("careers.tencent.com", "join.qq.com"),
        supported_variants=("experienced", "campus", "internship"),
        aliases=("Tencent",),
    ),
    OfficialSiteDescriptor(
        company_key="meituan",
        company_name="\u7f8e\u56e2",
        label="\u7f8e\u56e2\u5b98\u7f51",
        source_sites=("zhaopin.meituan.com",),
        supported_variants=("experienced",),
        aliases=("Meituan",),
    ),
    OfficialSiteDescriptor(
        company_key="pdd",
        company_name="\u62fc\u591a\u591a",
        label="\u62fc\u591a\u591a\u5b98\u7f51",
        source_sites=("careers.pddglobalhr.com",),
        supported_variants=("campus", "internship"),
        aliases=("PDD", "Pinduoduo"),
    ),
    OfficialSiteDescriptor(
        company_key="aliyun",
        company_name="\u963f\u91cc\u4e91",
        label="\u963f\u91cc\u4e91\u5b98\u7f51",
        source_sites=("careers.aliyun.com",),
        supported_variants=("experienced", "campus", "internship"),
        aliases=("Aliyun", "Alibaba Cloud"),
    ),
)

_DESCRIPTOR_BY_KEY = {item.company_key: item for item in OFFICIAL_SITE_DESCRIPTORS}
_DESCRIPTOR_BY_COMPANY = {
    name.casefold(): item
    for item in OFFICIAL_SITE_DESCRIPTORS
    for name in (item.company_name, *item.aliases)
}
_DESCRIPTOR_BY_SOURCE_SITE = {
    site.casefold(): item
    for item in OFFICIAL_SITE_DESCRIPTORS
    for site in item.source_sites
}


def list_official_sites() -> list[OfficialSiteDescriptor]:
    return list(OFFICIAL_SITE_DESCRIPTORS)


def get_official_site(company_key: str) -> OfficialSiteDescriptor:
    descriptor = _DESCRIPTOR_BY_KEY.get((company_key or "").strip())
    if not descriptor:
        raise KeyError(f"Unsupported official company key: {company_key}")
    return descriptor


def resolve_company_key(*, source_company: str = "", source_site: str = "") -> str | None:
    normalized_source_site = (source_site or "").strip().casefold()
    if normalized_source_site:
        descriptor = _DESCRIPTOR_BY_SOURCE_SITE.get(normalized_source_site)
        if descriptor:
            return descriptor.company_key

    normalized_company = (source_company or "").strip().casefold()
    if normalized_company:
        descriptor = _DESCRIPTOR_BY_COMPANY.get(normalized_company)
        if descriptor:
            return descriptor.company_key
    return None


def default_storage_state_path(*, company_key: str, account_id: str) -> Path:
    return settings.browser_dir / "official" / company_key / account_id / "storage-state.json"


def default_resume_asset_path(*, asset_id: str, source_filename: str) -> Path:
    suffix = Path(source_filename or "resume.pdf").suffix or ".pdf"
    return settings.resume_dir / "assets" / f"{asset_id}{suffix}"
