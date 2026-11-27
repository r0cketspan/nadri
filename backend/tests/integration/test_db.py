"""통합: 롤 권한·COMMENT·upsert 멱등 (I-5~I-7)."""

import uuid
from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

from nadri.core.db import create_engine, session_factory
from nadri.core.models.tour import TourItem
from nadri.core.tourapi import KST
from nadri.ingest.upsert import TourItemRecord, upsert_tour_item
from tests.core.test_config import EXPECTED_COMMENTS

pytestmark = pytest.mark.integration


async def test_tools_role_permissions(tools_settings):
    """I-5: nadri_tools는 tour_items 읽기만, ingest_runs 읽기·쓰기 거부, lightrag DB 접속 불가."""
    engine = create_engine(tools_settings)
    try:
        async with engine.connect() as c:
            await c.execute(text("SELECT count(*) FROM tour_items"))
        for sql in (
            "SELECT * FROM ingest_runs",
            "INSERT INTO tour_items (contentid, content_type_id, area, title, as_of) VALUES ('x', 12, '서울', 'x', now())",
        ):
            async with engine.connect() as c:
                with pytest.raises(DBAPIError):
                    await c.execute(text(sql))
    finally:
        await engine.dispose()

    other = create_engine(tools_settings.model_copy(update={"db_name": "lightrag"}))
    try:
        with pytest.raises(DBAPIError):
            async with other.connect() as c:
                await c.execute(text("SELECT 1"))
    finally:
        await other.dispose()


async def test_comments(app_settings):
    """I-6: 실 DB의 테이블·컬럼 COMMENT가 spec §3.2와 같다."""
    engine = create_engine(app_settings)
    try:
        async with engine.connect() as c:
            for table, (table_comment, cols) in EXPECTED_COMMENTS.items():
                got = await c.scalar(text("SELECT obj_description(CAST(:t AS regclass), 'pg_class')"), {"t": table})
                assert got == table_comment
                rows = await c.execute(text(
                    "SELECT a.attname, col_description(a.attrelid, a.attnum) FROM pg_attribute a "
                    "WHERE a.attrelid = CAST(:t AS regclass) AND a.attnum > 0 AND NOT a.attisdropped"
                ), {"t": table})
                assert dict(rows.all()) == cols
    finally:
        await engine.dispose()


async def test_upsert_idempotent(app_settings):
    """I-7: inserted → unchanged(updated_at 불변) → 값 변경 시 updated."""
    cid = f"test-01-{uuid.uuid4()}"
    now = datetime.now(KST)
    rec = TourItemRecord(cid, 12, "서울", None, "테스트", None, None, None, None, "09:00", None, None,
                         None, None, {}, None, now, now.date())
    engine = create_engine(app_settings)
    sf = session_factory(engine)
    try:
        async with sf() as s:
            assert await upsert_tour_item(s, rec) == "inserted"
            await s.commit()
            before = await s.scalar(select(TourItem.updated_at).where(TourItem.contentid == cid))
        async with sf() as s:
            assert await upsert_tour_item(s, replace(rec, detail_synced_at=datetime.now(KST))) == "unchanged"
            await s.commit()
            assert await s.scalar(select(TourItem.updated_at).where(TourItem.contentid == cid)) == before
        async with sf() as s:
            assert await upsert_tour_item(s, replace(rec, usetime="10:00")) == "updated"
            await s.commit()
    finally:
        async with sf() as s:
            await s.execute(delete(TourItem).where(TourItem.contentid == cid))
            await s.commit()
        await engine.dispose()
