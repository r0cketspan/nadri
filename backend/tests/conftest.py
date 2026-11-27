"""공통 테스트 도우미 — 픽스처 경로·설정 생성."""

import json
from pathlib import Path

import pytest

from nadri.core.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(rel: str) -> str:
    """fixtures 아래 파일을 문자열로 읽는다."""
    return (FIXTURES / rel).read_text(encoding="utf-8")


def load_item(rel: str):
    """TourAPI 픽스처 JSON에서 response.body.items.item 을 꺼낸다."""
    return json.loads(load_fixture(rel))["response"]["body"]["items"]["item"]


def make_settings(**overrides) -> Settings:
    """환경변수와 무관한 테스트용 Settings(필수값만 채움)."""
    values = {"db_user": "nadri_app", "db_password": "pw"}
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def settings() -> Settings:
    """기본 테스트 설정."""
    return make_settings()
