from __future__ import annotations

from .base import CareerSiteSource


SOURCES: tuple[CareerSiteSource, ...] = (
    CareerSiteSource(
        key="bytedance-experienced",
        company_name="\u5b57\u8282\u8df3\u52a8",
        entry_url="https://jobs.bytedance.com/",
        source_site="jobs.bytedance.com",
        collector_key="bytedance",
        variant="experienced",
        label="\u5b57\u8282\u8df3\u52a8\u793e\u62db",
    ),
    CareerSiteSource(
        key="bytedance-campus",
        company_name="\u5b57\u8282\u8df3\u52a8",
        entry_url="https://jobs.bytedance.com/campus",
        source_site="jobs.bytedance.com",
        collector_key="bytedance",
        variant="campus",
        label="\u5b57\u8282\u8df3\u52a8\u6821\u62db",
    ),
    CareerSiteSource(
        key="bytedance-internship",
        company_name="\u5b57\u8282\u8df3\u52a8",
        entry_url="https://jobs.bytedance.com/campus",
        source_site="jobs.bytedance.com",
        collector_key="bytedance",
        variant="internship",
        label="\u5b57\u8282\u8df3\u52a8\u5b9e\u4e60",
    ),
)


def load_sources() -> tuple[CareerSiteSource, ...]:
    return SOURCES


def get_available_variants() -> list[str]:
    return list(dict.fromkeys(source.variant for source in SOURCES))


def get_available_companies() -> list[str]:
    return list(dict.fromkeys(source.company_name for source in SOURCES))


def filter_sources(
    sources: tuple[CareerSiteSource, ...],
    variants: list[str] | None = None,
    companies: list[str] | None = None,
) -> tuple[CareerSiteSource, ...]:
    if not variants and not companies:
        return sources
    filtered = list(sources)
    if variants:
        filtered = [s for s in filtered if s.variant in variants]
    if companies:
        filtered = [s for s in filtered if s.company_name in companies]
    return tuple(filtered)
