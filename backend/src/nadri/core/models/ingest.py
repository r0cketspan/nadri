"""수집 실행 이력(ingest_runs)·수집 상태(ingest_state) ORM."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nadri.core.models import Base


class IngestRun(Base):
    """적재·재인덱싱 실행 한 번의 기록(시작·종료·결과·통계)."""

    __tablename__ = "ingest_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed')", name="ck_ingest_runs_status"),
        {"comment": "수집 실행 이력"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True, comment="실행 ID")
    kind: Mapped[str] = mapped_column(Text, nullable=False, comment="실행 종류")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="시작 일시"
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="종료 일시")
    status: Mapped[str] = mapped_column(Text, nullable=False, comment="결과")
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="처리 통계")
    lint: Mapped[dict | None] = mapped_column(JSONB, comment="점검 결과")
    error: Mapped[str | None] = mapped_column(Text, comment="오류 메시지")


class IngestState(Base):
    """키-값 수집 상태. 01은 'tourapi_calls:YYYY-MM-DD' → {"ingest": n, "live": 0} 호출 수 카운터만 쓴다."""

    __tablename__ = "ingest_state"
    __table_args__ = {"comment": "수집 상태"}

    key: Mapped[str] = mapped_column(Text, primary_key=True, comment="상태 키")
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="상태 값")
