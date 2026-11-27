"""ORM 공통 Base. 모델 모듈을 모두 import해 Base.metadata에 테이블이 등록되게 한다."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 nadri ORM 모델의 부모 클래스(Alembic target_metadata로 쓰임)."""


from nadri.core.models import ingest, tour  # noqa: E402,F401  (테이블 등록용)
