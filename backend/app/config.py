from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _looks_like_kimi_code_key(value: str) -> bool:
    return value.strip().startswith("sk-kimi-")


def _looks_like_moonshot_key(value: str) -> bool:
    value = value.strip()
    return value.startswith("sk-") and not value.startswith("sk-kimi-")


def _looks_like_seed_key(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F-]{36}", value.strip()))


def _read_key_from_file(var_name: str) -> str:
    """
    Local fallback for user-managed keys.ts.
    Supports:
      const travily_api_key = "..."
      const kimi_code_api_key = "..."
      const moonshot_api_key = "..."
      const seed_api_key = "..."
    """
    mapping = {
        "TAVILY_API_KEY": "travily_api_key",
        "KIMI_CODE_API_KEY": "kimi_code_api_key",
        "MOONSHOT_API_KEY": "moonshot_api_key",
        "SEED_API_KEY": "seed_api_key",
        "ARK_API_KEY": "seed_api_key",
    }
    target = mapping.get(var_name)
    if not target:
        return ""

    key_file = Path(__file__).resolve().parents[2] / "keys.ts"
    if not key_file.exists():
        return ""
    text = key_file.read_text(encoding="utf-8", errors="ignore")
    m = re.search(rf"{re.escape(target)}\s*=\s*\"([^\"]+)\"", text)
    if not m:
        return ""
    return m.group(1).strip()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "DebateAI"
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    app_env: str = os.getenv("APP_ENV", "development")

    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    reports_dir: Path = data_dir / "reports"
    sessions_dir: Path = data_dir / "sessions"

    ark_api_key: str = (
        os.getenv("ARK_API_KEY", "")
        or os.getenv("SEED_API_KEY", "")
        or _read_key_from_file("ARK_API_KEY")
        or _read_key_from_file("SEED_API_KEY")
    )
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_api_key: str = (
        os.getenv("OPENAI_API_KEY", "")
        or ark_api_key
        or os.getenv("MOONSHOT_API_KEY", "")
        or _read_key_from_file("MOONSHOT_API_KEY")
        or _read_key_from_file("KIMI_CODE_API_KEY")
    )
    openai_model: str = os.getenv("OPENAI_MODEL", "")
    openai_model_pro: str = os.getenv("OPENAI_MODEL_PRO", "ep-20260312221206-pqnpr")
    openai_max_output_tokens: int = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "32768"))

    search_provider: str = os.getenv("SEARCH_PROVIDER", "tavily")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "") or _read_key_from_file("TAVILY_API_KEY")

    default_debater_count: int = int(os.getenv("DEFAULT_DEBATER_COUNT", "3"))
    default_time_limit_sec: int = int(os.getenv("DEFAULT_TIME_LIMIT_SEC", "360"))
    default_max_turns: int = int(os.getenv("DEFAULT_MAX_TURNS", "24"))
    default_enable_debater_search: bool = _bool_env("DEFAULT_ENABLE_DEBATER_SEARCH", False)

    allow_unsafe_topics: bool = _bool_env("ALLOW_UNSAFE_TOPICS", False)


settings = Settings()

if not settings.openai_base_url:
    if settings.ark_api_key or _looks_like_seed_key(settings.openai_api_key):
        object.__setattr__(settings, "openai_base_url", "https://ark.cn-beijing.volces.com/api/v3")
    elif _looks_like_kimi_code_key(settings.openai_api_key):
        object.__setattr__(settings, "openai_base_url", "https://api.kimi.com/coding/v1")
    elif _looks_like_moonshot_key(settings.openai_api_key):
        object.__setattr__(settings, "openai_base_url", "https://api.moonshot.cn/v1")
    else:
        object.__setattr__(settings, "openai_base_url", "https://api.openai.com/v1")

if not settings.openai_model:
    if settings.ark_api_key or _looks_like_seed_key(settings.openai_api_key):
        object.__setattr__(settings, "openai_model", "doubao-seed-2-0-lite-260215")
    elif _looks_like_kimi_code_key(settings.openai_api_key):
        object.__setattr__(settings, "openai_model", "kimi-for-coding")
    elif _looks_like_moonshot_key(settings.openai_api_key):
        object.__setattr__(settings, "openai_model", "kimi-latest")
    else:
        object.__setattr__(settings, "openai_model", "gpt-4.1-mini")


def ensure_directories() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
