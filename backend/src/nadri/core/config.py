"""nadri 백엔드 공통 설정 — 컨테이너 환경변수에서 읽는다."""

import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    nadri 백엔드 공통 설정. 컨테이너 환경변수에서 읽는다(서비스마다 필요한 키만 주입됨).

    `.env` 파일은 직접 읽지 않는다 — compose가 서비스별로 필요한 값만 넣어 준다.
    비밀값은 SecretStr이라 repr·로그에 값이 나오지 않는다.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # DB 접속 (ingest = nadri_app, tour-tools = nadri_tools)
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "nadri"
    db_user: str
    db_password: SecretStr

    # TourAPI (ingest 전용)
    tourapi_service_key: SecretStr | None = None
    tourapi_base_url: str = "https://apis.data.go.kr/B551011/KorService2"
    tourapi_timeout_s: float = 15.0
    tourapi_daily_ingest_budget: int = 800

    # LightRAG·MCP 내부 호출
    lightrag_url: str = "http://lightrag:9621"
    lightrag_api_key: SecretStr | None = None
    tools_url: str = "http://tour-tools:8000/mcp"
    tools_api_key: SecretStr | None = None

    # 파일 위치
    wiki_dir: Path = Path("/data/wiki")
    raw_dir: Path = Path("/data/raw")

    # 검색·리랭크 조정값 (A9 대안: 후보 20·max_length 256)
    rag_candidates: int = 30
    rag_top_k: int = 5
    reranker_model_path: str = "/opt/models/bge-reranker-v2-m3"
    reranker_max_length: int = 512

    # LightRAG 인덱싱 처리 대기 상한(초)
    index_timeout_s: int = 1800

    @property
    def database_url(self) -> str:
        """
        asyncpg 접속 URL을 만든다.

        Returns:
            `postgresql+asyncpg://user:pw@host:port/db` — 사용자·비밀번호는 URL 인코딩한다
            (비밀번호에 @ : / 가 있어도 깨지지 않게).
        """
        user = quote(self.db_user, safe="")
        password = quote(self.db_password.get_secret_value(), safe="")
        return f"postgresql+asyncpg://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache
def get_settings() -> Settings:
    """
    프로세스 전체에서 하나의 Settings를 돌려준다(처음 호출 때 환경변수를 읽음).

    Returns:
        캐시된 Settings
    """
    return Settings()


def require(value: SecretStr | None, name: str) -> str:
    """
    필수 비밀값을 꺼낸다. 없으면 한국어 안내와 함께 종료 코드 2로 끝낸다.

    Args:
        value: 설정의 비밀값 필드
        name: 환경변수 이름(안내 문구용)

    Returns:
        비밀값 문자열

    Raises:
        SystemExit(2): 값이 없거나 빈 문자열일 때
    """
    # 1) 값이 비었으면 어떤 환경변수를 채워야 하는지 알려 주고 종료한다
    if value is None or not value.get_secret_value():
        print(f"설정 오류: 환경변수 {name} 가 비어 있습니다. .env에 값을 넣고 다시 실행하세요.", file=sys.stderr)
        raise SystemExit(2)
    # 2) 값이 있으면 평문으로 꺼내 돌려준다
    return value.get_secret_value()
