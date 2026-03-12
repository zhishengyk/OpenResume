from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import settings


@dataclass(frozen=True)
class OfficialSiteDescriptor:
    company_key: str
    company_name: str
    label: str
    login_url: str
    source_sites: tuple[str, ...]
    supported_variants: tuple[str, ...]
    session_check_url: str | None = None
    aliases: tuple[str, ...] = ()
    supports_auto_submit: bool = True


ALL_VARIANTS = ("experienced", "campus", "internship")


OFFICIAL_SITE_DESCRIPTORS: tuple[OfficialSiteDescriptor, ...] = (
    OfficialSiteDescriptor(
        company_key="bytedance",
        company_name="\u5b57\u8282\u8df3\u52a8",
        label="\u5b57\u8282\u8df3\u52a8\u5b98\u7f51",
        login_url="https://jobs.bytedance.com/experienced/login",
        session_check_url="https://jobs.bytedance.com/experienced/login",
        source_sites=("jobs.bytedance.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("ByteDance",),
    ),
    OfficialSiteDescriptor(
        company_key="tencent",
        company_name="\u817e\u8baf",
        label="\u817e\u8baf\u5b98\u7f51",
        login_url="https://careers.tencent.com/login.html?state=https%3A%2F%2Fcareers.tencent.com%2F",
        session_check_url="https://careers.tencent.com/login.html?state=https%3A%2F%2Fcareers.tencent.com%2F",
        source_sites=("careers.tencent.com", "join.qq.com"),
        supported_variants=ALL_VARIANTS,
        aliases=("Tencent", "QQ"),
    ),
    OfficialSiteDescriptor(
        company_key="taobao",
        company_name="\u6dd8\u5929\u96c6\u56e2",
        label="\u6dd8\u5929\u96c6\u56e2\u5b98\u7f51",
        login_url="https://talent.taotian.com/",
        session_check_url="https://talent.taotian.com/",
        source_sites=("talent.taotian.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("Taotian", "Taobao"),
    ),
    OfficialSiteDescriptor(
        company_key="aliyun",
        company_name="\u963f\u91cc\u4e91",
        label="\u963f\u91cc\u4e91\u5b98\u7f51",
        login_url="https://careers.aliyun.com/off-campus/home?lang=zh",
        session_check_url="https://careers.aliyun.com/off-campus/home?lang=zh",
        source_sites=("careers.aliyun.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("Aliyun", "Alibaba Cloud"),
    ),
    OfficialSiteDescriptor(
        company_key="alibaba_holding",
        company_name="\u963f\u91cc\u63a7\u80a1",
        label="\u963f\u91cc\u63a7\u80a1\u5b98\u7f51",
        login_url="https://talent-holding.alibaba.com/",
        session_check_url="https://talent-holding.alibaba.com/",
        source_sites=("talent-holding.alibaba.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("Alibaba Holding", "Alibaba Holdings"),
    ),
    OfficialSiteDescriptor(
        company_key="meituan",
        company_name="\u7f8e\u56e2",
        label="\u7f8e\u56e2\u5b98\u7f51",
        login_url="https://zhaopin.meituan.com/web/login?redirectUrl=https%3A%2F%2Fzhaopin.meituan.com%2Fweb%2Fhome",
        session_check_url="https://zhaopin.meituan.com/web/login?redirectUrl=https%3A%2F%2Fzhaopin.meituan.com%2Fweb%2Fhome",
        source_sites=("zhaopin.meituan.com",),
        supported_variants=("experienced",),
        aliases=("Meituan",),
    ),
    OfficialSiteDescriptor(
        company_key="pdd",
        company_name="\u62fc\u591a\u591a",
        label="\u62fc\u591a\u591a\u5b98\u7f51",
        login_url="https://careers.pddglobalhr.com/campus/",
        session_check_url="https://careers.pddglobalhr.com/campus/",
        source_sites=("careers.pddglobalhr.com",),
        supported_variants=("campus", "internship"),
        aliases=("PDD", "Pinduoduo"),
    ),
    OfficialSiteDescriptor(
        company_key="kuaishou",
        company_name="\u5feb\u624b",
        label="\u5feb\u624b\u5b98\u7f51",
        login_url="https://zhaopin.kuaishou.cn/#/official/login/",
        session_check_url="https://zhaopin.kuaishou.cn/#/official/login/",
        source_sites=("zhaopin.kuaishou.cn", "campus.kuaishou.cn"),
        supported_variants=ALL_VARIANTS,
        aliases=("Kuaishou", "KuaiShou"),
    ),
    OfficialSiteDescriptor(
        company_key="jd",
        company_name="\u4eac\u4e1c",
        label="\u4eac\u4e1c\u5b98\u7f51",
        login_url="https://passport.jd.com/new/login.aspx?ReturnUrl=https%3A%2F%2Fzhaopin.jd.com%2Ferror",
        session_check_url="https://passport.jd.com/new/login.aspx?ReturnUrl=https%3A%2F%2Fzhaopin.jd.com%2Ferror",
        source_sites=("zhaopin.jd.com", "campus.jd.com"),
        supported_variants=ALL_VARIANTS,
        aliases=("JD", "JD.com"),
    ),
    OfficialSiteDescriptor(
        company_key="ant",
        company_name="\u8682\u8681\u96c6\u56e2",
        label="\u8682\u8681\u96c6\u56e2\u5b98\u7f51",
        login_url="https://talent.antgroup.com/login",
        session_check_url="https://talent.antgroup.com/login",
        source_sites=("talent.antgroup.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("Ant Group", "Ant"),
    ),
    OfficialSiteDescriptor(
        company_key="amap",
        company_name="\u9ad8\u5fb7\u5730\u56fe",
        label="\u9ad8\u5fb7\u5730\u56fe\u5b98\u7f51",
        login_url="https://talent.amap.com/off-campus/position-list?lang=zh",
        session_check_url="https://talent.amap.com/off-campus/position-list?lang=zh",
        source_sites=("talent.amap.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("AMap", "Gaode"),
    ),
    OfficialSiteDescriptor(
        company_key="eleme",
        company_name="\u997f\u4e86\u4e48",
        label="\u997f\u4e86\u4e48\u5b98\u7f51",
        login_url="https://talent.ele.me/off-campus/position-list?lang=zh",
        session_check_url="https://talent.ele.me/off-campus/position-list?lang=zh",
        source_sites=("talent.ele.me",),
        supported_variants=ALL_VARIANTS,
        aliases=("Eleme", "Ele.me"),
    ),
    OfficialSiteDescriptor(
        company_key="aidc",
        company_name="\u963f\u91cc\u56fd\u9645",
        label="\u963f\u91cc\u56fd\u9645\u5b98\u7f51",
        login_url="https://aidc-jobs.alibaba.com/off-campus/position-list?lang=zh",
        session_check_url="https://aidc-jobs.alibaba.com/off-campus/position-list?lang=zh",
        source_sites=("aidc-jobs.alibaba.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("AIDC", "Alibaba International"),
    ),
    OfficialSiteDescriptor(
        company_key="xiaohongshu",
        company_name="\u5c0f\u7ea2\u4e66",
        label="\u5c0f\u7ea2\u4e66\u5b98\u7f51",
        login_url="https://job.xiaohongshu.com/login",
        session_check_url="https://job.xiaohongshu.com/login",
        source_sites=("job.xiaohongshu.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("Xiaohongshu", "RED"),
    ),
    OfficialSiteDescriptor(
        company_key="bilibili",
        company_name="\u54d4\u54e9\u54d4\u54e9",
        label="\u54d4\u54e9\u54d4\u54e9\u5b98\u7f51",
        login_url="https://jobs.bilibili.com/",
        session_check_url="https://jobs.bilibili.com/",
        source_sites=("jobs.bilibili.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("Bilibili", "B\u7ad9"),
    ),
    OfficialSiteDescriptor(
        company_key="dewu",
        company_name="\u5f97\u7269",
        label="\u5f97\u7269\u5b98\u7f51",
        login_url="https://poizon.jobs.feishu.cn/index",
        session_check_url="https://poizon.jobs.feishu.cn/index",
        source_sites=("poizon.jobs.feishu.cn", "campus.dewu.com"),
        supported_variants=ALL_VARIANTS,
        aliases=("Dewu", "Poizon"),
    ),
    OfficialSiteDescriptor(
        company_key="freshippo",
        company_name="\u76d2\u9a6c",
        label="\u76d2\u9a6c\u5b98\u7f51",
        login_url="https://hire.freshippo.com/?lang=zh",
        session_check_url="https://hire.freshippo.com/?lang=zh",
        source_sites=("hire.freshippo.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("Freshippo", "Hema"),
    ),
    OfficialSiteDescriptor(
        company_key="mihoyo",
        company_name="\u7c73\u54c8\u6e38",
        label="\u7c73\u54c8\u6e38\u5b98\u7f51",
        login_url="https://jobs.mihoyo.com/recommendation/login",
        session_check_url="https://jobs.mihoyo.com/recommendation/login",
        source_sites=("jobs.mihoyo.com",),
        supported_variants=ALL_VARIANTS,
        aliases=("miHoYo", "Mihoyo"),
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
