from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Literal

from .base import ApplyExecutionOutcome, ApplyExecutionRequest, AutomationPage


LoginLaunchMode = Literal["direct", "click", "alibaba_embed"]


@dataclass(frozen=True)
class OfficialDriverConfig:
    company_key: str
    display_name: str
    login_markers: tuple[str, ...]
    captcha_markers: tuple[str, ...]
    form_open_selectors: tuple[str, ...]
    resume_upload_selectors: tuple[str, ...]
    full_name_selectors: tuple[str, ...]
    headline_selectors: tuple[str, ...]
    final_submit_selectors: tuple[str, ...]
    login_launch_mode: LoginLaunchMode = "direct"
    login_open_selectors: tuple[str, ...] = ()
    login_ready_wait_ms: int = 1200
    post_launch_wait_ms: int = 1200


COMMON_FORM_OPEN_SELECTORS = (
    "[data-openresume='open-apply']",
    "button:has-text('\u6295\u9012')",
    "button:has-text('\u7533\u8bf7')",
    "button:has-text('Apply')",
    "text=\u7acb\u5373\u7533\u8bf7",
)
COMMON_RESUME_UPLOAD_SELECTORS = (
    "[data-openresume='resume-upload']",
    "input[type='file']",
)
COMMON_FULL_NAME_SELECTORS = (
    "[data-openresume='full-name']",
    "input[name='name']",
    "input[name='fullName']",
    "input[placeholder*='\u59d3\u540d']",
)
COMMON_HEADLINE_SELECTORS = (
    "[data-openresume='headline']",
    "input[name='headline']",
    "textarea[name='headline']",
    "input[placeholder*='\u804c\u4f4d']",
)
COMMON_FINAL_SUBMIT_SELECTORS = (
    "[data-openresume='submit']",
    "button:has-text('\u786e\u8ba4\u63d0\u4ea4')",
    "button:has-text('\u63d0\u4ea4\u7533\u8bf7')",
    "button:has-text('\u63d0\u4ea4')",
    "button:has-text('\u786e\u8ba4\u6295\u9012')",
    "button:has-text('Submit')",
)
COMMON_LOGIN_MARKERS = (
    "\u767b\u5f55",
    "sign in",
    "login",
    "\u8d26\u53f7\u767b\u5f55",
)
COMMON_CAPTCHA_MARKERS = (
    "\u9a8c\u8bc1\u7801",
    "captcha",
    "\u4eba\u673a\u9a8c\u8bc1",
    "\u6ed1\u52a8\u9a8c\u8bc1",
)
ALIBABA_LOGIN_MARKERS = COMMON_LOGIN_MARKERS + (
    "\u652f\u4ed8\u5b9d\u767b\u5f55",
    "\u6dd8\u5b9d\u4f1a\u5458\u767b\u5f55",
    "mini-login-embedder",
)


def _config(
    *,
    company_key: str,
    display_name: str,
    login_markers: tuple[str, ...] = COMMON_LOGIN_MARKERS,
    login_launch_mode: LoginLaunchMode = "direct",
    login_open_selectors: tuple[str, ...] = (),
    login_ready_wait_ms: int = 1200,
    post_launch_wait_ms: int = 1200,
) -> OfficialDriverConfig:
    return OfficialDriverConfig(
        company_key=company_key,
        display_name=display_name,
        login_markers=login_markers,
        captcha_markers=COMMON_CAPTCHA_MARKERS,
        form_open_selectors=COMMON_FORM_OPEN_SELECTORS,
        resume_upload_selectors=COMMON_RESUME_UPLOAD_SELECTORS,
        full_name_selectors=COMMON_FULL_NAME_SELECTORS,
        headline_selectors=COMMON_HEADLINE_SELECTORS,
        final_submit_selectors=COMMON_FINAL_SUBMIT_SELECTORS,
        login_launch_mode=login_launch_mode,
        login_open_selectors=login_open_selectors,
        login_ready_wait_ms=login_ready_wait_ms,
        post_launch_wait_ms=post_launch_wait_ms,
    )


def _alibaba_config(company_key: str, display_name: str) -> OfficialDriverConfig:
    return _config(
        company_key=company_key,
        display_name=display_name,
        login_markers=ALIBABA_LOGIN_MARKERS,
        login_launch_mode="alibaba_embed",
        login_ready_wait_ms=1800,
        post_launch_wait_ms=1800,
    )


CONFIGS: dict[str, OfficialDriverConfig] = {
    "bytedance": _config(
        company_key="bytedance",
        display_name="\u5b57\u8282\u8df3\u52a8",
    ),
    "tencent": _config(
        company_key="tencent",
        display_name="\u817e\u8baf",
        login_markers=COMMON_LOGIN_MARKERS + ("\u626b\u7801\u767b\u5f55", "QQ\u767b\u5f55"),
    ),
    "taobao": _alibaba_config("taobao", "\u6dd8\u5929\u96c6\u56e2"),
    "aliyun": _alibaba_config("aliyun", "\u963f\u91cc\u4e91"),
    "alibaba_holding": _alibaba_config("alibaba_holding", "\u963f\u91cc\u63a7\u80a1"),
    "meituan": _config(
        company_key="meituan",
        display_name="\u7f8e\u56e2",
        login_markers=COMMON_LOGIN_MARKERS + ("\u7f8e\u56e2\u62db\u8058",),
    ),
    "pdd": _config(
        company_key="pdd",
        display_name="\u62fc\u591a\u591a",
        login_markers=COMMON_LOGIN_MARKERS + ("\u767b\u5f55/\u6ce8\u518c", "\u624b\u673a\u53f7"),
        login_launch_mode="click",
        login_open_selectors=("a.index_loginBtn__WPrQQ",),
        login_ready_wait_ms=1800,
    ),
    "kuaishou": _config(
        company_key="kuaishou",
        display_name="\u5feb\u624b",
        login_markers=COMMON_LOGIN_MARKERS + ("\u5feb\u624b", "\u626b\u7801\u767b\u5f55"),
    ),
    "jd": _config(
        company_key="jd",
        display_name="\u4eac\u4e1c",
        login_markers=COMMON_LOGIN_MARKERS + ("\u4eac\u4e1c\u767b\u5f55", "\u626b\u7801\u767b\u5f55"),
    ),
    "ant": _config(
        company_key="ant",
        display_name="\u8682\u8681\u96c6\u56e2",
        login_markers=COMMON_LOGIN_MARKERS + ("\u8682\u8681", "\u652f\u4ed8\u5b9d"),
    ),
    "amap": _alibaba_config("amap", "\u9ad8\u5fb7\u5730\u56fe"),
    "eleme": _alibaba_config("eleme", "\u997f\u4e86\u4e48"),
    "aidc": _alibaba_config("aidc", "\u963f\u91cc\u56fd\u9645"),
    "xiaohongshu": _config(
        company_key="xiaohongshu",
        display_name="\u5c0f\u7ea2\u4e66",
        login_markers=COMMON_LOGIN_MARKERS + ("\u5c0f\u7ea2\u4e66", "\u9a8c\u8bc1\u7801\u767b\u5f55"),
    ),
    "bilibili": _config(
        company_key="bilibili",
        display_name="\u54d4\u54e9\u54d4\u54e9",
        login_markers=COMMON_LOGIN_MARKERS + ("\u54d4\u54e9\u54d4\u54e9",),
        login_launch_mode="click",
        login_open_selectors=(".pill-btn:has-text('\u767b\u5f55')", ".pill-btn"),
        login_ready_wait_ms=2200,
    ),
    "dewu": _config(
        company_key="dewu",
        display_name="\u5f97\u7269",
        login_markers=COMMON_LOGIN_MARKERS + ("\u98de\u4e66",),
        login_launch_mode="click",
        login_open_selectors=("a[href*='/login']",),
        login_ready_wait_ms=2200,
    ),
    "freshippo": _alibaba_config("freshippo", "\u76d2\u9a6c"),
    "mihoyo": _config(
        company_key="mihoyo",
        display_name="\u7c73\u54c8\u6e38",
        login_markers=COMMON_LOGIN_MARKERS + ("\u7c73\u54c8\u6e38", "\u901a\u884c\u8bc1"),
    ),
}


def _build_alibaba_login_embed_script(display_name: str) -> str:
    title = json.dumps(f"{display_name}\u767b\u5f55")
    return f"""
() => {{
  if (!window.MiniLoginEmbedder) {{
    return false;
  }}
  const hostId = 'openresume-alibaba-login-host';
  let host = document.getElementById(hostId);
  if (!host) {{
    host = document.createElement('div');
    host.id = hostId;
    host.style.position = 'fixed';
    host.style.right = '24px';
    host.style.top = '24px';
    host.style.zIndex = '99999';
    host.style.background = '#ffffff';
    host.style.borderRadius = '16px';
    host.style.boxShadow = '0 24px 80px rgba(15, 23, 42, 0.24)';
    host.style.padding = '12px';
    document.body.appendChild(host);
  }}
  host.innerHTML = '';
  const title = document.createElement('div');
  title.innerText = {title};
  title.style.fontFamily = 'sans-serif';
  title.style.fontSize = '14px';
  title.style.fontWeight = '600';
  title.style.marginBottom = '8px';
  host.appendChild(title);
  const mount = document.createElement('div');
  mount.id = 'openresume-alibaba-login-iframe';
  host.appendChild(mount);
  const instance = new window.MiniLoginEmbedder();
  instance.init({{
    targetId: 'openresume-alibaba-login-iframe',
    iframeWidth: 360,
    iframeHeight: 420,
  }});
  return true;
}}
"""


class GenericOfficialDriver:
    def __init__(self, config: OfficialDriverConfig) -> None:
        self.config = config

    async def launch_login(
        self,
        page: AutomationPage,
        *,
        target_url: str,
    ) -> None:
        await page.goto(target_url)
        await page.wait_for_timeout(self.config.login_ready_wait_ms)

        if self.config.login_launch_mode == "click":
            clicked_selector = await page.try_click(list(self.config.login_open_selectors))
            if not clicked_selector:
                raise RuntimeError(
                    f"{self.config.display_name} \u9996\u9875\u672a\u627e\u5230\u53ef\u7528\u7684\u767b\u5f55\u5165\u53e3\u3002"
                )
            await page.wait_for_timeout(self.config.post_launch_wait_ms)
            return

        if self.config.login_launch_mode == "alibaba_embed":
            launched = await page.evaluate(
                _build_alibaba_login_embed_script(self.config.display_name)
            )
            if launched is not True:
                raise RuntimeError(
                    f"{self.config.display_name} \u5b98\u7f51\u672a\u52a0\u8f7d\u963f\u91cc\u767b\u5f55\u7ec4\u4ef6\u3002"
                )
            await page.wait_for_timeout(self.config.post_launch_wait_ms)

    async def check_session(
        self,
        page: AutomationPage,
        *,
        target_url: str,
    ) -> tuple[bool, str]:
        await page.goto(target_url)
        await page.wait_for_timeout(min(1000, self.config.login_ready_wait_ms))
        if await page.content_contains(list(self.config.login_markers)):
            return (
                False,
                f"{self.config.display_name} \u5f53\u524d\u672a\u767b\u5f55\uff0c\u8bf7\u5148\u5728\u8d26\u53f7\u6c60\u5b8c\u6210\u5b98\u7f51\u767b\u5f55\u3002",
            )
        if await page.content_contains(list(self.config.captcha_markers)):
            return (
                False,
                f"{self.config.display_name} \u89e6\u53d1\u4e86\u9a8c\u8bc1\u6216\u4eba\u5de5\u6821\u9a8c\uff0c\u8bf7\u91cd\u65b0\u767b\u5f55\u3002",
            )
        return True, f"{self.config.display_name} \u767b\u5f55\u7f13\u5b58\u53ef\u7528\u3002"

    async def run(
        self,
        page: AutomationPage,
        request: ApplyExecutionRequest,
    ) -> ApplyExecutionOutcome:
        await page.goto(request.apply_url)
        if await page.content_contains(list(self.config.login_markers)):
            return ApplyExecutionOutcome(
                status="failed",
                message=(
                    f"{self.config.display_name} "
                    "\u767b\u5f55\u7f13\u5b58\u5931\u6548\uff0c\u8bf7\u5148\u5728\u8d26\u53f7\u6c60\u91cd\u65b0\u767b\u5f55\u3002"
                ),
                launch_url=request.apply_url,
                context={"company_key": self.config.company_key, "phase": "login"},
            )

        clicked_open_selector = await page.try_click(list(self.config.form_open_selectors))
        uploaded_selector = await page.try_set_input_files(
            list(self.config.resume_upload_selectors),
            request.resume_path,
        )
        full_name_selector = await page.try_fill(
            list(self.config.full_name_selectors),
            request.full_name,
        )
        headline_selector = await page.try_fill(
            list(self.config.headline_selectors),
            request.headline,
        )

        if await page.content_contains(list(self.config.captcha_markers)):
            return ApplyExecutionOutcome(
                status="needs_verification",
                message=(
                    f"{self.config.display_name} "
                    "\u89e6\u53d1\u4e86\u9a8c\u8bc1\u7801\u6216\u4eba\u5de5\u6821\u9a8c\uff0c\u8bf7\u4eba\u5de5\u7ee7\u7eed\u3002"
                ),
                verification_url=request.apply_url,
                launch_url=request.apply_url,
                context={"company_key": self.config.company_key, "phase": "captcha"},
            )

        if request.execution_mode == "semi_auto":
            return ApplyExecutionOutcome(
                status="prepared",
                message=(
                    f"{self.config.display_name} "
                    "\u5df2\u81ea\u52a8\u586b\u5145\u5e76\u505c\u5728\u6700\u7ec8\u63d0\u4ea4\u524d\u3002"
                ),
                verification_url=request.apply_url,
                launch_url=request.apply_url,
                context={
                    "company_key": self.config.company_key,
                    "clicked_open_selector": clicked_open_selector or "",
                    "uploaded_selector": uploaded_selector or "",
                    "full_name_selector": full_name_selector or "",
                    "headline_selector": headline_selector or "",
                },
            )

        clicked_submit_selector = await page.try_click(list(self.config.final_submit_selectors))
        if clicked_submit_selector:
            return ApplyExecutionOutcome(
                status="submitted",
                message=f"{self.config.display_name} \u5df2\u6267\u884c\u81ea\u52a8\u63d0\u4ea4\u3002",
                launch_url=request.apply_url,
                context={
                    "company_key": self.config.company_key,
                    "submit_selector": clicked_submit_selector,
                    "clicked_open_selector": clicked_open_selector or "",
                    "uploaded_selector": uploaded_selector or "",
                },
            )

        return ApplyExecutionOutcome(
            status="prepared",
            message=(
                f"{self.config.display_name} "
                "\u672a\u8bc6\u522b\u5230\u6700\u7ec8\u63d0\u4ea4\u63a7\u4ef6\uff0c\u5df2\u505c\u5728\u63d0\u4ea4\u524d\u3002"
            ),
            verification_url=request.apply_url,
            launch_url=request.apply_url,
            context={
                "company_key": self.config.company_key,
                "clicked_open_selector": clicked_open_selector or "",
                "uploaded_selector": uploaded_selector or "",
                "full_name_selector": full_name_selector or "",
                "headline_selector": headline_selector or "",
            },
        )


DRIVERS = {
    company_key: GenericOfficialDriver(config)
    for company_key, config in CONFIGS.items()
}


def get_official_driver(company_key: str) -> GenericOfficialDriver:
    driver = DRIVERS.get((company_key or "").strip())
    if not driver:
        raise KeyError(f"Unsupported official company key: {company_key}")
    return driver
