from dataclasses import dataclass
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT_DIR.parent


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
    official_source_file: Path = Path(
        os.getenv("OPENRESUME_OFFICIAL_SOURCE_FILE", str(PROJECT_ROOT / "url.md"))
    )
    official_request_timeout_seconds: float = float(
        os.getenv("OPENRESUME_OFFICIAL_REQUEST_TIMEOUT_SECONDS", "12")
    )
    official_source_limit: int = int(
        os.getenv("OPENRESUME_OFFICIAL_SOURCE_LIMIT", "10")
    )
    official_job_limit_per_source: int = int(
        os.getenv("OPENRESUME_OFFICIAL_JOB_LIMIT_PER_SOURCE", "4")
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
