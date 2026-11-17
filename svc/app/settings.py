"""运行配置：全部来自环境变量，本地跑时给合理默认值。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # svc/


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class Settings:
    # 数据库：Docker 内是 /data/notice.db；本地跑可设成 ./data/notice.db
    db_path: str = _env("DB_PATH", str(BASE_DIR / "data" / "notice.db"))
    sources_file: str = _env("SOURCES_FILE", str(BASE_DIR / "data" / "sources.yaml"))
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
