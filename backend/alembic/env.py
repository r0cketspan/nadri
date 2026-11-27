"""Alembic 실행 환경 — nadri 설정의 DB 주소로 async 엔진을 만들어 테이블 생성 스크립트를 적용한다."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from nadri.core.config import get_settings
from nadri.core.db import create_engine
from nadri.core.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    """
    동기 연결 위에서 아직 적용되지 않은 스크립트를 실행한다.

    Args:
        connection: run_sync가 넘겨주는 동기 연결
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """async 엔진(asyncpg)으로 접속해 do_run_migrations를 실행하고 엔진을 정리한다."""
    # 1) 환경변수 설정으로 엔진 생성(롤 nadri_app — 테이블 소유자)
    engine = create_engine(get_settings())
    # 2) 동기 API인 Alembic을 run_sync로 실행
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("오프라인(SQL 출력) 모드는 쓰지 않습니다")
asyncio.run(run_async_migrations())
