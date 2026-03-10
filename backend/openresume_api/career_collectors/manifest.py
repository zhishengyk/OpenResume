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
)


def load_sources() -> tuple[CareerSiteSource, ...]:
    return SOURCES
