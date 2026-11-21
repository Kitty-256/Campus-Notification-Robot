"""部署版本信息：让「机器上跑的是哪一版代码」可被验证。

来源优先级：
1. 环境变量 GIT_COMMIT（Docker / CI 用）
2. svc/app/_build.json —— 由 scripts/deploy_local.ps1 在每次部署时写入

这个文件本身不进版本库（见 .gitignore），因为它是「部署事实」，不是「代码」。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_BUILD_FILE = _APP_DIR / "_build.json"


def info() -> dict:
    data = {"version": "dev", "commit": "", "built_at": ""}
    try:
        if _BUILD_FILE.exists():
            data.update(json.loads(_BUILD_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    commit = os.environ.get("GIT_COMMIT", "").strip()
    if commit:
        data["commit"] = commit
    return data
