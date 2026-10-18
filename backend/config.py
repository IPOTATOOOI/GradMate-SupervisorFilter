from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _path_env(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    base_url: str | None
    model_id: str
    temperature: float
    timeout_seconds: float
    provider: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model_id)


@dataclass(frozen=True)
class ServerSettings:
    host: str
    port: int


@dataclass(frozen=True)
class WorkspaceSettings:
    work_root: Path
    word_reports_dir: Path
    screenshots_dir: Path
    system_prompt_file: Path


@dataclass(frozen=True)
class BaoyanDDLSettings:
    source_url: str
    cache_ttl_seconds: int


@dataclass(frozen=True)
class BrowserSettings:
    chromedriver_path: Path | None
    chrome_binary_path: Path | None
    headless: bool
    search_url_template: str
    max_pages: int
    llm_assist: bool
    llm_extract: bool
    llm_extract_max_records: int
    llm_page_text_limit: int
    llm_extract_max_pages: int
    final_supervisor_limit: int


@dataclass(frozen=True)
class SchoolDirectorySettings:
    file_path: Path


@dataclass(frozen=True)
class EmailSettings:
    send_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    from_email: str
    from_name: str
    reply_to: str
    use_tls: bool
    use_ssl: bool
    timeout_seconds: int

    @property
    def configured(self) -> bool:
        return bool(
            self.send_enabled
            and self.smtp_host
            and self.smtp_port
            and self.smtp_username
            and self.smtp_password
            and self.from_email
        )


@dataclass(frozen=True)
class SecuritySettings:
    cors_origins: list[str]


WORK_ROOT = _path_env("WORK_ROOT", BASE_DIR / "workspace")
WORD_REPORTS_DIR = _path_env("WORD_REPORTS_DIR", WORK_ROOT / "word_reports")
SCREENSHOTS_DIR = _path_env("SCREENSHOTS_DIR", WORK_ROOT / "screenshots")
SYSTEM_PROMPT_FILE = _path_env("SYSTEM_PROMPT_FILE", BASE_DIR / "system_prompt.md")
DEFAULT_BAOYAN_DDL_SOURCE_URL = (
    "https://raw.githubusercontent.com/CS-BAOYAN/CS-BAOYAN-DDL/main/src/data/schools.json"
)
DEFAULT_SCHOOL_DIRECTORY_FILE = BASE_DIR.parent / "GradMate_软科Top40计算机院系官网.xlsx"


def get_model_settings() -> ModelSettings:
    ark_api_key = os.getenv("ARK_API_KEY", "").strip()
    ark_model = os.getenv("MODEL_ID", "").strip()
    if ark_api_key and ark_model:
        return ModelSettings(
            api_key=ark_api_key,
            base_url=os.getenv("ARK_BASE_URL", "").strip() or None,
            model_id=ark_model,
            temperature=_float_env("MODEL_TEMPERATURE", 0.3),
            timeout_seconds=max(10, _float_env("MODEL_TIMEOUT_SECONDS", 90)),
            provider="ark",
        )

    return ModelSettings(
        api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        base_url=os.getenv("OPENAI_BASE_URL", "").strip() or None,
        model_id=os.getenv("OPENAI_MODEL", "").strip(),
        temperature=_float_env("MODEL_TEMPERATURE", 0.3),
        timeout_seconds=max(10, _float_env("MODEL_TIMEOUT_SECONDS", 90)),
        provider="openai-compatible",
    )


def get_server_settings() -> ServerSettings:
    return ServerSettings(
        host=os.getenv("BACKEND_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int_env("BACKEND_PORT", 8000),
    )


def get_workspace_settings() -> WorkspaceSettings:
    return WorkspaceSettings(
        work_root=WORK_ROOT,
        word_reports_dir=WORD_REPORTS_DIR,
        screenshots_dir=SCREENSHOTS_DIR,
        system_prompt_file=SYSTEM_PROMPT_FILE,
    )


def get_baoyan_ddl_settings() -> BaoyanDDLSettings:
    return BaoyanDDLSettings(
        source_url=os.getenv("BAOYAN_DDL_SOURCE_URL", DEFAULT_BAOYAN_DDL_SOURCE_URL).strip()
        or DEFAULT_BAOYAN_DDL_SOURCE_URL,
        cache_ttl_seconds=_int_env("BAOYAN_DDL_CACHE_TTL_SECONDS", 1800),
    )


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def get_browser_settings() -> BrowserSettings:
    chrome_binary = os.getenv("CHROME_BINARY_PATH", "").strip()
    chromedriver = os.getenv("CHROMEDRIVER_PATH", "").strip()
    return BrowserSettings(
        chromedriver_path=_path_env("CHROMEDRIVER_PATH", Path(chromedriver)) if chromedriver else None,
        chrome_binary_path=_path_env("CHROME_BINARY_PATH", Path(chrome_binary)) if chrome_binary else None,
        headless=_bool_env("BROWSER_HEADLESS", True),
        search_url_template=os.getenv(
            "BROWSER_SEARCH_URL_TEMPLATE",
            "https://www.bing.com/search?q={query}",
        ).strip()
        or "https://www.bing.com/search?q={query}",
        max_pages=_int_env("BROWSER_MAX_PAGES", 12),
        llm_assist=_bool_env("BROWSER_LLM_ASSIST", True),
        llm_extract=_bool_env("BROWSER_LLM_EXTRACT", True),
        llm_extract_max_records=max(3, min(_int_env("BROWSER_LLM_MAX_RECORDS", 5), 5)),
        llm_page_text_limit=max(1000, min(_int_env("BROWSER_LLM_TEXT_LIMIT", 6000), 12000)),
        llm_extract_max_pages=max(1, min(_int_env("BROWSER_LLM_EXTRACT_MAX_PAGES", 3), 12)),
        final_supervisor_limit=max(3, min(_int_env("BROWSER_FINAL_SUPERVISOR_LIMIT", 5), 5)),
    )


def get_school_directory_settings() -> SchoolDirectorySettings:
    return SchoolDirectorySettings(
        file_path=_path_env("SCHOOL_DIRECTORY_FILE", DEFAULT_SCHOOL_DIRECTORY_FILE),
    )


def get_email_settings() -> EmailSettings:
    username = os.getenv("SMTP_USERNAME", "").strip()
    return EmailSettings(
        send_enabled=_bool_env("EMAIL_SEND_ENABLED", False),
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=_int_env("SMTP_PORT", 465),
        smtp_username=username,
        smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
        from_email=os.getenv("SMTP_FROM_EMAIL", "").strip() or username,
        from_name=os.getenv("SMTP_FROM_NAME", "GradMate").strip() or "GradMate",
        reply_to=os.getenv("SMTP_REPLY_TO", "").strip(),
        use_tls=_bool_env("SMTP_USE_TLS", False),
        use_ssl=_bool_env("SMTP_USE_SSL", True),
        timeout_seconds=_int_env("SMTP_TIMEOUT_SECONDS", 20),
    )


def get_security_settings() -> SecuritySettings:
    raw_origins = os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return SecuritySettings(cors_origins=origins)


def public_config() -> dict[str, object]:
    model = get_model_settings()
    server = get_server_settings()
    workspace = get_workspace_settings()
    ddl = get_baoyan_ddl_settings()
    browser = get_browser_settings()
    school_directory = get_school_directory_settings()
    email = get_email_settings()
    return {
        "model_provider": model.provider,
        "model_id": model.model_id,
        "model_configured": model.configured,
        "base_url": model.base_url,
        "temperature": model.temperature,
        "model_timeout_seconds": model.timeout_seconds,
        "backend_host": server.host,
        "backend_port": server.port,
        "workspace_configured": workspace.work_root.exists(),
        "baoyan_ddl_source_url": ddl.source_url,
        "baoyan_ddl_cache_ttl_seconds": ddl.cache_ttl_seconds,
        "chromedriver_configured": bool(browser.chromedriver_path),
        "browser_headless": browser.headless,
        "browser_max_pages": browser.max_pages,
        "browser_llm_assist": browser.llm_assist,
        "browser_llm_extract": browser.llm_extract,
        "browser_llm_max_records": browser.llm_extract_max_records,
        "browser_llm_text_limit": browser.llm_page_text_limit,
        "browser_llm_extract_max_pages": browser.llm_extract_max_pages,
        "browser_final_supervisor_limit": browser.final_supervisor_limit,
        "school_directory_available": school_directory.file_path.exists(),
        "smtp_configured": email.configured,
        "smtp_host": email.smtp_host,
        "smtp_port": email.smtp_port,
    }
