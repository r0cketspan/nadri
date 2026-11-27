"""관광 정보·위키 페이지·수집 실행 이력·수집 상태 테이블 생성, nadri_tools 읽기 권한 부여

Revision ID: 0001_tour_ingest
Revises:
Create Date: 2026-11-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_tour_ingest"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """테이블 4개(한글 COMMENT 포함) → 인덱스 → nadri_tools에 tour_items·wiki_pages SELECT만 부여."""
    # 1) 관광 정보
    op.create_table(
        "tour_items",
        sa.Column("contentid", sa.Text(), primary_key=True, comment="관광지 ID"),
        sa.Column("content_type_id", sa.Integer(), nullable=False, comment="관광 유형"),
        sa.Column("area", sa.Text(), nullable=False, comment="지역"),
        sa.Column("sigungu_code", sa.Text(), comment="시군구 코드"),
        sa.Column("title", sa.Text(), nullable=False, comment="명칭"),
        sa.Column("addr", sa.Text(), comment="주소"),
        sa.Column("lat", sa.Float(precision=53), comment="위도"),
        sa.Column("lng", sa.Float(precision=53), comment="경도"),
        sa.Column("tel", sa.Text(), comment="전화번호"),
        sa.Column("usetime", sa.Text(), comment="이용시간"),
        sa.Column("fee", sa.Text(), comment="이용요금"),
        sa.Column("restdate", sa.Text(), comment="휴무일"),
        sa.Column("event_start", sa.Date(), comment="행사 시작일"),
        sa.Column("event_end", sa.Date(), comment="행사 종료일"),
        sa.Column("extra", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"), comment="유형별 상세"),
        sa.Column("modifiedtime", sa.DateTime(timezone=True), comment="원천 수정 일시"),
        sa.Column("detail_synced_at", sa.DateTime(timezone=True), comment="상세 수집 일시"),
        sa.Column("as_of", sa.Date(), nullable=False, comment="기준일"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), comment="삭제 일시"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="수정 일시"),
        comment="관광 정보",
    )

    # 2) 위키 페이지
    op.create_table(
        "wiki_pages",
        sa.Column("path", sa.Text(), primary_key=True, comment="페이지 경로"),
        sa.Column("kind", sa.Text(), nullable=False, comment="페이지 종류"),
        sa.Column("contentid", sa.Text(), sa.ForeignKey("tour_items.contentid"), comment="관광지 ID"),
        sa.Column("title", sa.Text(), nullable=False, comment="제목"),
        sa.Column("area", sa.Text(), comment="지역"),
        sa.Column("sigungu_code", sa.Text(), comment="시군구 코드"),
        sa.Column("as_of", sa.Date(), comment="기준일"),
        sa.Column("content_hash", sa.Text(), comment="내용 해시"),
        sa.Column("lightrag_doc_id", sa.Text(), comment="RAG 문서 ID"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), comment="인덱싱 일시"),
        sa.CheckConstraint("kind IN ('entity', 'hub')", name="ck_wiki_pages_kind"),
        comment="위키 페이지",
    )

    # 3) 수집 실행 이력
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, comment="실행 ID"),
        sa.Column("kind", sa.Text(), nullable=False, comment="실행 종류"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="시작 일시"),
        sa.Column("finished_at", sa.DateTime(timezone=True), comment="종료 일시"),
        sa.Column("status", sa.Text(), nullable=False, comment="결과"),
        sa.Column("stats", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"), comment="처리 통계"),
        sa.Column("lint", JSONB(), comment="점검 결과"),
        sa.Column("error", sa.Text(), comment="오류 메시지"),
        sa.CheckConstraint("status IN ('running', 'done', 'failed')", name="ck_ingest_runs_status"),
        comment="수집 실행 이력",
    )

    # 4) 수집 상태
    op.create_table(
        "ingest_state",
        sa.Column("key", sa.Text(), primary_key=True, comment="상태 키"),
        sa.Column("value", JSONB(), nullable=False, comment="상태 값"),
        comment="수집 상태",
    )

    # 5) 인덱스 — 50~수천 건 규모라 지역·유형 하나만
    op.create_index(
        "ix_tour_items_area_type", "tour_items", ["area", "content_type_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 6) tour-tools 롤은 두 테이블 읽기만(롤·CONNECT·USAGE는 01-init.sh)
    op.execute("GRANT SELECT ON tour_items, wiki_pages TO nadri_tools")


def downgrade() -> None:
    """권한 회수 → 테이블 4개 삭제(생성 역순)."""
    op.execute("REVOKE SELECT ON tour_items, wiki_pages FROM nadri_tools")
    op.drop_table("ingest_state")
    op.drop_table("ingest_runs")
    op.drop_table("wiki_pages")
    op.drop_table("tour_items")
