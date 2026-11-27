"""통합 테스트 공통 — 실 compose(dev 덮어쓰기 포트)와 레포 루트 .env의 실 키가 필요하다.

실행: DB_HOST=127.0.0.1 LIGHTRAG_URL=http://127.0.0.1:9621 TOOLS_URL=http://127.0.0.1:8001/mcp \\
      uv run pytest -m integration -q
"""

import json
import os
from pathlib import Path

import pytest

from nadri.core.config import Settings

ROOT_ENV = Path(__file__).parents[3] / ".env"


def read_env() -> dict[str, str]:
    """레포 루트 .env(키=값)와 현재 환경변수를 합친다(환경변수 우선)."""
    values: dict[str, str] = {}
    if ROOT_ENV.exists():
        for line in ROOT_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip("'\"")
    values.update(os.environ)
    return values


def settings_for(role: str) -> Settings:
    """롤(nadri_app/nadri_tools)별 접속 설정. 주소는 환경변수(DB_HOST 등)로 바꾼다."""
    env = read_env()
    password = env["APP_DB_PASSWORD"] if role == "nadri_app" else env["TOOLS_DB_PASSWORD"]
    return Settings(
        db_host=env.get("DB_HOST", "127.0.0.1"),
        db_port=int(env.get("DB_PORT", "5432")),
        db_user=role,
        db_password=password,
        lightrag_url=env.get("LIGHTRAG_URL", "http://127.0.0.1:9621"),
        lightrag_api_key=env.get("LIGHTRAG_API_KEY"),
        tools_url=env.get("TOOLS_URL", "http://127.0.0.1:8001/mcp"),
        tools_api_key=env.get("TOOLS_API_KEY"),
    )


def as_json(result):
    """어댑터 툴 결과(문자열 또는 content 블록 목록)를 dict로."""
    if isinstance(result, list):
        result = next(b["text"] for b in result if isinstance(b, dict) and b.get("type") == "text")
    return json.loads(result) if isinstance(result, str) else result


@pytest.fixture
def app_settings() -> Settings:
    """nadri_app 롤 설정."""
    return settings_for("nadri_app")


@pytest.fixture
def tools_settings() -> Settings:
    """nadri_tools 롤 설정."""
    return settings_for("nadri_tools")
