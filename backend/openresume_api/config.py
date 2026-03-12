from dataclasses import dataclass
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT_DIR.parent


def _default_company_worker_count() -> int:
    configured = os.getenv("OPENRESUME_OFFICIAL_COMPANY_WORKER_COUNT")
    if configured:
        return int(configured)
    cpu_count = os.cpu_count() or 4
    return max(4, min(20, cpu_count))


def _default_page_worker_count() -> int:
    configured = os.getenv("OPENRESUME_OFFICIAL_PAGE_WORKER_COUNT")
    if configured:
        return int(configured)
    cpu_count = os.cpu_count() or 4
    return max(2, min(8, cpu_count))


@dataclass(frozen=True)
class Settings:
    api_host: str = os.getenv("OPENRESUME_API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("OPENRESUME_API_PORT", "38417"))
    storage_dir: Path = Path(
        os.getenv("OPENRESUME_STORAGE_DIR", str(ROOT_DIR / "storage"))
    )
    database_filename: str = "openresume.db"
    default_rule_manifest_url: str | None = os.getenv(
        "OPENRESUME_RULE_MANIFEST_URL", None
    )
    llm_provider: str = os.getenv("OPENRESUME_LLM_PROVIDER", "heuristic")
    openai_base_url: str | None = os.getenv("OPENRESUME_OPENAI_BASE_URL", None)
    openai_api_key: str | None = os.getenv("OPENRESUME_OPENAI_API_KEY", None)
    openai_model: str | None = os.getenv("OPENRESUME_OPENAI_MODEL", None)
    official_request_timeout_seconds: float = float(
        os.getenv("OPENRESUME_OFFICIAL_REQUEST_TIMEOUT_SECONDS", "12")
    )
    official_job_limit_per_source: int = int(
        os.getenv("OPENRESUME_OFFICIAL_JOB_LIMIT_PER_SOURCE", "400")
    )
    search_match_limit: int = int(
        os.getenv("OPENRESUME_SEARCH_MATCH_LIMIT", "200")
    )
    search_company_job_limit: int = int(
        os.getenv("OPENRESUME_SEARCH_COMPANY_JOB_LIMIT", "200")
    )
    official_company_worker_count: int = _default_company_worker_count()
    official_page_worker_count: int = _default_page_worker_count()
    official_detail_worker_count: int = int(
        os.getenv("OPENRESUME_OFFICIAL_DETAIL_WORKER_COUNT", "6")
    )
    official_bytedance_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_BYTEDANCE_PAGE_LIMIT", "8")
    )
    official_bytedance_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_BYTEDANCE_PAGE_SIZE", "100")
    )
    official_tencent_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_TENCENT_PAGE_LIMIT", "8")
    )
    official_tencent_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_TENCENT_PAGE_SIZE", "50")
    )
    official_tme_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_TME_PAGE_LIMIT", "8")
    )
    official_tme_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_TME_PAGE_SIZE", "20")
    )
    official_baidu_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_BAIDU_PAGE_LIMIT", "8")
    )
    official_baidu_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_BAIDU_PAGE_SIZE", "20")
    )
    official_didi_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_DIDI_PAGE_LIMIT", "8")
    )
    official_didi_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_DIDI_PAGE_SIZE", "20")
    )
    official_ctrip_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_CTRIP_PAGE_LIMIT", "8")
    )
    official_ctrip_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_CTRIP_PAGE_SIZE", "50")
    )
    official_netease_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_NETEASE_PAGE_LIMIT", "8")
    )
    official_netease_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_NETEASE_PAGE_SIZE", "50")
    )
    official_quark_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_QUARK_PAGE_LIMIT", "8")
    )
    official_quark_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_QUARK_PAGE_SIZE", "50")
    )
    official_taobao_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_TAOBAO_PAGE_LIMIT", "8")
    )
    official_taobao_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_TAOBAO_PAGE_SIZE", "50")
    )
    official_aliyun_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ALIYUN_PAGE_LIMIT", "8")
    )
    official_aliyun_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ALIYUN_PAGE_SIZE", "50")
    )
    official_alibaba_holding_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ALIBABA_HOLDING_PAGE_LIMIT", "8")
    )
    official_alibaba_holding_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ALIBABA_HOLDING_PAGE_SIZE", "50")
    )
    official_meituan_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_MEITUAN_PAGE_LIMIT", "8")
    )
    official_meituan_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_MEITUAN_PAGE_SIZE", "50")
    )
    official_pdd_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_PDD_PAGE_LIMIT", "8")
    )
    official_pdd_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_PDD_PAGE_SIZE", "50")
    )
    official_kuaishou_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_KUAISHOU_PAGE_LIMIT", "8")
    )
    official_kuaishou_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_KUAISHOU_PAGE_SIZE", "50")
    )
    official_jd_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_JD_PAGE_LIMIT", "8")
    )
    official_jd_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_JD_PAGE_SIZE", "50")
    )
    official_ant_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ANT_PAGE_LIMIT", "8")
    )
    official_ant_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ANT_PAGE_SIZE", "50")
    )
    official_amap_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_AMAP_PAGE_LIMIT", "8")
    )
    official_amap_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_AMAP_PAGE_SIZE", "50")
    )
    official_eleme_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ELEME_PAGE_LIMIT", "8")
    )
    official_eleme_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_ELEME_PAGE_SIZE", "50")
    )
    official_aidc_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_AIDC_PAGE_LIMIT", "8")
    )
    official_aidc_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_AIDC_PAGE_SIZE", "50")
    )
    official_xiaohongshu_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_XIAOHONGSHU_PAGE_LIMIT", "8")
    )
    official_xiaohongshu_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_XIAOHONGSHU_PAGE_SIZE", "100")
    )
    official_bilibili_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_BILIBILI_PAGE_LIMIT", "8")
    )
    official_bilibili_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_BILIBILI_PAGE_SIZE", "100")
    )
    official_dewu_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_DEWU_PAGE_LIMIT", "8")
    )
    official_dewu_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_DEWU_PAGE_SIZE", "100")
    )
    official_freshippo_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_FRESHIPPO_PAGE_LIMIT", "8")
    )
    official_freshippo_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_FRESHIPPO_PAGE_SIZE", "100")
    )
    official_mihoyo_page_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_MIHOYO_PAGE_LIMIT", "8")
    )
    official_mihoyo_page_size: int = int(
        os.getenv("OPENRESUME_OFFICIAL_MIHOYO_PAGE_SIZE", "100")
    )
    disable_browser_open: bool = (
        os.getenv("OPENRESUME_DISABLE_BROWSER_OPEN", "0") == "1"
    )

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.storage_dir / self.database_filename}"

    @property
    def database_path(self) -> Path:
        return self.storage_dir / self.database_filename

    @property
    def resume_dir(self) -> Path:
        return self.storage_dir / "resumes"

    @property
    def log_dir(self) -> Path:
        return self.storage_dir / "logs"

    @property
    def browser_dir(self) -> Path:
        return self.storage_dir / "browser"

    @property
    def rules_dir(self) -> Path:
        return self.storage_dir / "rules"

    @property
    def cache_dir(self) -> Path:
        return self.storage_dir / "cache"


settings = Settings()

for directory in [
    settings.storage_dir,
    settings.resume_dir,
    settings.log_dir,
    settings.browser_dir,
    settings.rules_dir,
    settings.cache_dir,
]:
    directory.mkdir(parents=True, exist_ok=True)
