"""변환·upsert 문 단위테스트 (U-UP)."""

import re
from datetime import date, datetime

from sqlalchemy.dialects import postgresql

from nadri.core.tourapi import KST
from nadri.ingest.upsert import build_record, build_upsert_stmt, clean_text
from tests.conftest import load_item

FETCHED = datetime(2026, 11, 21, 10, 0, tzinfo=KST)


def fixtures():
    """경복궁 상세 3종 픽스처(dict 복사본)."""
    return dict(load_item("tourapi/common_126508.json")), dict(load_item("tourapi/intro_126508.json")), [
        dict(r) for r in load_item("tourapi/info_126508.json")
    ]


def compile_sql(stmt):
    """PostgreSQL 방언으로 컴파일(값은 바인드로 남음)."""
    return stmt.compile(dialect=postgresql.dialect())


def test_clean_br():
    """U-UP-1: <br> → 줄바꿈."""
    assert clean_text("09:00~18:00<br>입장마감 17:00") == "09:00~18:00\n입장마감 17:00"


def test_clean_link():
    """U-UP-2: 링크 태그 제거, 글자만."""
    assert clean_text('<a href="http://x">http://x</a>') == "http://x"


def test_clean_entities_and_blank():
    """U-UP-3: 엔티티 해제, 공백·None → None."""
    assert clean_text("A &amp; B") == "A & B"
    assert clean_text("  ") is None
    assert clean_text(None) is None


def test_build_record_basic():
    """U-UP-4: 기본 매핑."""
    common, intro, info = fixtures()
    rec = build_record("서울", common, intro, info, FETCHED)
    assert (rec.contentid, rec.title, rec.area, rec.content_type_id) == ("126508", "경복궁", "서울", 12)
    assert rec.lat == float(common["mapy"]) and rec.lng == float(common["mapx"])
    assert rec.as_of == date(2026, 11, 21) and rec.detail_synced_at == FETCHED
    assert rec.modifiedtime == datetime(2026, 11, 20, 10, 30, tzinfo=KST)
    assert rec.sigungu_code == "23" and rec.restdate == "매주 화요일"
    assert rec.fee == "대인 3,000원\n소인 1,500원"  # '입 장 료'(띄어쓰기)도 요금으로 인식
    assert rec.extra["homepage"] == "https://royal.khs.go.kr/gbg"
    assert "광화문 & 근정전" in rec.extra["overview"]


def test_addr_without_addr2():
    """U-UP-5: addr2 빈 값 → addr == addr1."""
    common, intro, info = fixtures()
    common["addr2"] = ""
    assert build_record("서울", common, intro, info, FETCHED).addr == common["addr1"]


def test_zero_coords():
    """U-UP-6: mapx 0, mapy 빈 값 → None."""
    common, intro, info = fixtures()
    common.update(mapx="0", mapy="")
    rec = build_record("서울", common, intro, info, FETCHED)
    assert rec.lat is None and rec.lng is None


def test_tel_fallback_infocenter():
    """U-UP-7: common tel 없음 → intro infocenter."""
    common, intro, info = fixtures()
    common.pop("tel")
    intro["infocenter"] = "02-3700-3900"
    assert build_record("서울", common, intro, info, FETCHED).tel == "02-3700-3900"


def test_fee_from_info():
    """U-UP-8: '이용요금' 항목에서 요금."""
    common, intro, _ = fixtures()
    info = [{"infoname": "화장실", "infotext": "있음"}, {"infoname": "이용요금", "infotext": "3,000원"}]
    assert build_record("서울", common, intro, info, FETCHED).fee == "3,000원"


def test_bad_modifiedtime():
    """U-UP-9: 형식 다른 modifiedtime → None(예외 없음)."""
    common, intro, info = fixtures()
    common["modifiedtime"] = "2026-11-21"
    assert build_record("서울", common, intro, info, FETCHED).modifiedtime is None


def test_extra_intro_unmapped_only():
    """U-UP-10: 매핑 안 된 intro 필드만, 빈 값 제외."""
    common, _, info = fixtures()
    intro = {"contentid": "126508", "contenttypeid": "12", "usetime": "09:00", "parking": "가능", "chkpet": ""}
    assert build_record("서울", common, intro, info, FETCHED).extra["intro"] == {"parking": "가능"}


def test_deterministic():
    """U-UP-11: 같은 입력 → 같은 결과."""
    a = build_record("서울", *fixtures(), FETCHED)
    b = build_record("서울", *fixtures(), FETCHED)
    assert a == b


def test_upsert_stmt_shape():
    """U-UP-12: ON CONFLICT DO UPDATE … WHERE IS DISTINCT FROM, RETURNING xmax, 비교 목록에 as_of 있고 detail_synced_at 없음."""
    sql = str(compile_sql(build_upsert_stmt(build_record("서울", *fixtures(), FETCHED))))
    assert "ON CONFLICT (contentid) DO UPDATE" in sql
    assert "IS DISTINCT FROM" in sql and "RETURNING" in sql and "xmax" in sql
    where = sql.split("DO UPDATE", 1)[1].split(" WHERE ", 1)[1].split("RETURNING")[0]
    assert "as_of" in where and "detail_synced_at" not in where
    assert re.search(r"SET .*detail_synced_at", sql, re.S)  # 값은 갱신 시 함께 바뀐다


def test_upsert_stmt_binds_values():
    """U-UP-13: 위험한 제목은 SQL 문자열이 아니라 바인드 파라미터에."""
    common, intro, info = fixtures()
    common["title"] = "경복궁'; DROP TABLE x;--"
    compiled = compile_sql(build_upsert_stmt(build_record("서울", common, intro, info, FETCHED)))
    assert "DROP TABLE" not in str(compiled)
    assert "경복궁'; DROP TABLE x;--" in compiled.params.values()
