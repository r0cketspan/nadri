"""관광 정보(tour_items)·위키 페이지(wiki_pages) ORM. COMMENT는 ERD 한글 명칭과 같아야 한다."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nadri.core.models import Base


class TourItem(Base):
    """TourAPI 관광 항목 한 건(정형 데이터). 삭제는 deleted_at으로 표시만 한다(soft delete)."""

    __tablename__ = "tour_items"
    __table_args__ = (
        Index(
            "ix_tour_items_area_type", "area", "content_type_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"comment": "관광 정보"},
    )

    contentid: Mapped[str] = mapped_column(Text, primary_key=True, comment="관광지 ID")
    content_type_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="관광 유형")
    area: Mapped[str] = mapped_column(Text, nullable=False, comment="지역")
    sigungu_code: Mapped[str | None] = mapped_column(Text, comment="시군구 코드")
    title: Mapped[str] = mapped_column(Text, nullable=False, comment="명칭")
    addr: Mapped[str | None] = mapped_column(Text, comment="주소")
    lat: Mapped[float | None] = mapped_column(Float(precision=53), comment="위도")
    lng: Mapped[float | None] = mapped_column(Float(precision=53), comment="경도")
    tel: Mapped[str | None] = mapped_column(Text, comment="전화번호")
    usetime: Mapped[str | None] = mapped_column(Text, comment="이용시간")
    fee: Mapped[str | None] = mapped_column(Text, comment="이용요금")
    restdate: Mapped[str | None] = mapped_column(Text, comment="휴무일")
    event_start: Mapped[date | None] = mapped_column(Date, comment="행사 시작일")
    event_end: Mapped[date | None] = mapped_column(Date, comment="행사 종료일")
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment="유형별 상세")
    modifiedtime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="원천 수정 일시")
    detail_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="상세 수집 일시")
    as_of: Mapped[date] = mapped_column(Date, nullable=False, comment="기준일")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="삭제 일시")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="수정 일시"
    )


class WikiPage(Base):
    """위키 마크다운 페이지 한 개의 메타와 LightRAG 인덱싱 상태."""

    __tablename__ = "wiki_pages"
    __table_args__ = (
        CheckConstraint("kind IN ('entity', 'hub')", name="ck_wiki_pages_kind"),
        {"comment": "위키 페이지"},
    )

    path: Mapped[str] = mapped_column(Text, primary_key=True, comment="페이지 경로")
    kind: Mapped[str] = mapped_column(Text, nullable=False, comment="페이지 종류")
    contentid: Mapped[str | None] = mapped_column(
        Text, ForeignKey("tour_items.contentid"), comment="관광지 ID"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, comment="제목")
    area: Mapped[str | None] = mapped_column(Text, comment="지역")
    sigungu_code: Mapped[str | None] = mapped_column(Text, comment="시군구 코드")
    as_of: Mapped[date | None] = mapped_column(Date, comment="기준일")
    content_hash: Mapped[str | None] = mapped_column(Text, comment="내용 해시")
    lightrag_doc_id: Mapped[str | None] = mapped_column(Text, comment="RAG 문서 ID")
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="인덱싱 일시")
