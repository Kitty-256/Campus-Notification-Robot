"""运行配置：全部来自环境变量，本地跑时给合理默认值。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # svc/
REPO_DIR = BASE_DIR.parent                                  # 仓库根


def _load_env_file() -> None:
    """读 .env（仓库根或 svc/ 下）。已存在的环境变量优先，不覆盖。

    刻意不引 python-dotenv：20 行够用，少一个依赖。
    """
    for p in (REPO_DIR / ".env", BASE_DIR / ".env"):
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_env_file()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _resolve(p: str, default_rel: str) -> str:
    """相对路径按仓库根解析，避免本地跑时写到了意料之外的位置。"""
    raw = p or default_rel
    path = Path(raw)
    return str(path) if path.is_absolute() else str((REPO_DIR / raw).resolve())


class Settings:
    # 数据库：默认仓库根下 data/notice.db；Docker 里由 compose 覆盖成 /data/notice.db
    db_path: str = _resolve(_env("DB_PATH"), "data/notice.db")
    sources_file: str = _resolve(_env("SOURCES_FILE"), "data/sources.yaml")
    admin_token: str = _env("ADMIN_TOKEN", "change-me")

    # 只用于展示的时区偏移（Asia/Shanghai），避免依赖 tzdata
    tz_offset_hours: int = int(_env("TZ_OFFSET_HOURS", "8"))

    # LLM
    llm_base_url: str = _env("LLM_BASE_URL", "https://api.deepseek.com/v1")
    llm_api_key: str = _env("LLM_API_KEY")
    llm_model: str = _env("LLM_MODEL", "deepseek-chat")
    llm_timeout: int = int(_env("LLM_TIMEOUT", "60"))

    # 抓取节奏
    crawl_interval_min: int = int(_env("CRAWL_INTERVAL_MIN", "60"))
    crawl_delay_min: float = float(_env("CRAWL_DELAY_MIN", "1"))
    crawl_delay_max: float = float(_env("CRAWL_DELAY_MAX", "3"))

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )


settings = Settings()
