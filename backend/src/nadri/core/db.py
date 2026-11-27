"""async DB 엔진·세션 팩토리."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from nadri.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """
    설정의 접속 정보로 asyncpg 엔진을 만든다.

    Args:
        settings: DB 접속 정보가 든 설정

    Returns:
        pool_size=5, pool_pre_ping=True 인 AsyncEngine (실제 접속은 첫 쿼리 때)
    """
    return create_async_engine(settings.database_url, pool_size=5, pool_pre_ping=True)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    커밋 뒤에도 객체 속성을 다시 읽지 않는(expire_on_commit=False) 세션 팩토리를 만든다.

    Args:
        engine: create_engine으로 만든 엔진

    Returns:
        async 세션 팩토리
    """
    return async_sessionmaker(engine, expire_on_commit=False)
