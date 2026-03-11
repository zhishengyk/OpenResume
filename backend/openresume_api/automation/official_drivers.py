from __future__ import annotations

from dataclasses import dataclass

from .base import ApplyExecutionOutcome, ApplyExecutionRequest, AutomationPage


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


COMMON_FORM_OPEN_SELECTORS = (
    "[data-openresume='open-apply']",
    "button:has-text('投递')",
    "button:has-text('申请')",
    "button:has-text('Apply')",
    "text=立即申请",
)
COMMON_RESUME_UPLOAD_SELECTORS = (
    "[data-openresume='resume-upload']",
    "input[type='file']",
)
COMMON_FULL_NAME_SELECTORS = (
    "[data-openresume='full-name']",
    "input[name='name']",
    "input[name='fullName']",
    "input[placeholder*='姓名']",
)
COMMON_HEADLINE_SELECTORS = (
    "[data-openresume='headline']",
    "input[name='headline']",
    "textarea[name='headline']",
    "input[placeholder*='职位']",
)
COMMON_FINAL_SUBMIT_SELECTORS = (
    "[data-openresume='submit']",
    "button:has-text('确认提交')",
    "button:has-text('提交申请')",
    "button:has-text('提交')",
    "button:has-text('确认投递')",
    "button:has-text('Submit')",
)
COMMON_LOGIN_MARKERS = (
    "登录",
    "sign in",
    "login",
    "账号登录",
)
COMMON_CAPTCHA_MARKERS = (
    "验证码",
    "captcha",
    "人机验证",
)


CONFIGS: dict[str, OfficialDriverConfig] = {
    "bytedance": OfficialDriverConfig(
        company_key="bytedance",
        display_name="字节跳动",
        login_markers=COMMON_LOGIN_MARKERS,
        captcha_markers=COMMON_CAPTCHA_MARKERS,
        form_open_selectors=COMMON_FORM_OPEN_SELECTORS,
        resume_upload_selectors=COMMON_RESUME_UPLOAD_SELECTORS,
        full_name_selectors=COMMON_FULL_NAME_SELECTORS,
        headline_selectors=COMMON_HEADLINE_SELECTORS,
        final_submit_selectors=COMMON_FINAL_SUBMIT_SELECTORS,
    ),
    "tencent": OfficialDriverConfig(
        company_key="tencent",
        display_name="腾讯",
        login_markers=COMMON_LOGIN_MARKERS + ("QQ登录",),
        captcha_markers=COMMON_CAPTCHA_MARKERS,
        form_open_selectors=COMMON_FORM_OPEN_SELECTORS,
        resume_upload_selectors=COMMON_RESUME_UPLOAD_SELECTORS,
        full_name_selectors=COMMON_FULL_NAME_SELECTORS,
        headline_selectors=COMMON_HEADLINE_SELECTORS,
        final_submit_selectors=COMMON_FINAL_SUBMIT_SELECTORS,
    ),
    "meituan": OfficialDriverConfig(
        company_key="meituan",
        display_name="美团",
        login_markers=COMMON_LOGIN_MARKERS + ("美团招聘",),
        captcha_markers=COMMON_CAPTCHA_MARKERS,
        form_open_selectors=COMMON_FORM_OPEN_SELECTORS,
        resume_upload_selectors=COMMON_RESUME_UPLOAD_SELECTORS,
        full_name_selectors=COMMON_FULL_NAME_SELECTORS,
        headline_selectors=COMMON_HEADLINE_SELECTORS,
        final_submit_selectors=COMMON_FINAL_SUBMIT_SELECTORS,
    ),
    "pdd": OfficialDriverConfig(
        company_key="pdd",
        display_name="拼多多",
        login_markers=COMMON_LOGIN_MARKERS + ("拼多多",),
        captcha_markers=COMMON_CAPTCHA_MARKERS,
        form_open_selectors=COMMON_FORM_OPEN_SELECTORS,
        resume_upload_selectors=COMMON_RESUME_UPLOAD_SELECTORS,
        full_name_selectors=COMMON_FULL_NAME_SELECTORS,
        headline_selectors=COMMON_HEADLINE_SELECTORS,
        final_submit_selectors=COMMON_FINAL_SUBMIT_SELECTORS,
    ),
    "aliyun": OfficialDriverConfig(
        company_key="aliyun",
        display_name="阿里云",
        login_markers=COMMON_LOGIN_MARKERS + ("阿里云",),
        captcha_markers=COMMON_CAPTCHA_MARKERS,
        form_open_selectors=COMMON_FORM_OPEN_SELECTORS,
        resume_upload_selectors=COMMON_RESUME_UPLOAD_SELECTORS,
        full_name_selectors=COMMON_FULL_NAME_SELECTORS,
        headline_selectors=COMMON_HEADLINE_SELECTORS,
        final_submit_selectors=COMMON_FINAL_SUBMIT_SELECTORS,
    ),
}


class GenericOfficialDriver:
    def __init__(self, config: OfficialDriverConfig) -> None:
        self.config = config

    async def run(
        self,
        page: AutomationPage,
        request: ApplyExecutionRequest,
    ) -> ApplyExecutionOutcome:
        await page.goto(request.apply_url)
        if await page.content_contains(list(self.config.login_markers)):
            return ApplyExecutionOutcome(
                status="needs_verification",
                message=f"{self.config.display_name} 登录态不可复用，请先完成人工验证。",
                verification_url=request.apply_url,
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
                message=f"{self.config.display_name} 触发验证码或人工校验，请人工继续。",
                verification_url=request.apply_url,
                launch_url=request.apply_url,
                context={"company_key": self.config.company_key, "phase": "captcha"},
            )

        if request.execution_mode == "semi_auto":
            return ApplyExecutionOutcome(
                status="prepared",
                message=f"{self.config.display_name} 已完成预填，停在最终提交前。",
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

        clicked_submit_selector = await page.try_click(
            list(self.config.final_submit_selectors)
        )
        if clicked_submit_selector:
            return ApplyExecutionOutcome(
                status="submitted",
                message=f"{self.config.display_name} 已执行自动提交。",
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
                f"{self.config.display_name} 页面未识别到最终提交控件，已停在提交前，"
                "请人工确认后继续。"
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
