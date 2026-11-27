"""정형 조회 단위테스트 (U-DQ) — SQL은 PostgreSQL 방언으로 컴파일해 문자열·바인드를 검사."""

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from nadri.tools.data_query import (
    ITEM_COLUMNS,
    DataQueryParams,
    NearPoint,
    apply_near,
    bounding_box,
    build_select,
    escape_like,
    haversine_km,
    row_to_item,
)


def compiled(**kw):
    """파라미터로 Select를 만들어 (SQL 문자열, 바인드 dict)로."""
    c = build_select(DataQueryParams(**kw)).compile(dialect=postgresql.dialect())
    return str(c), c.params


@pytest.mark.parametrize("kw", [
    {"area": "부산"},                                                     # U-DQ-1
    {"area": "서울", "limit": 0},                                         # U-DQ-2
    {"area": "서울", "sort": "distance"},                                 # U-DQ-4
    {"area": "서울", "near": {"lat": 37.5, "lng": 127.0, "radius_km": 25}},  # U-DQ-5
    {"area": "서울", "near": {"lat": 37.5, "lng": 127.0, "radius_km": 0}},   # U-DQ-5
    {"area": "서울", "content_type": 13},                                 # U-DQ-7
    {"area": "서울", "sigungu_code": "1; DROP"},                          # U-DQ-8
])
def test_invalid_params(kw):
    """U-DQ-1·2·4·5·7·8: 검증 오류(ValueError 계열)."""
    with pytest.raises(ValidationError):
        DataQueryParams(**kw)


def test_limit_capped():
    """U-DQ-3: limit 100 → 20."""
    assert DataQueryParams(area="서울", limit=100).limit == 20


def test_blank_keyword():
    """U-DQ-6: 공백 키워드 → None."""
    assert DataQueryParams(area="서울", keyword="   ").keyword is None


def test_escape_like():
    """U-DQ-9: \\ % _ 이스케이프."""
    assert escape_like("50%_할인\\") == "50\\%\\_할인\\\\"


def test_basic_select():
    """U-DQ-10: 삭제 제외·지역 바인드·제목순·LIMIT 10."""
    sql, params = compiled(area="서울")
    assert "deleted_at IS NULL" in sql and "tour_items.area = %(area_1)s" in sql
    assert "ORDER BY tour_items.title, tour_items.contentid" in sql and "LIMIT" in sql
    assert "서울" in params.values() and 10 in params.values()


def test_keyword_is_bound():
    """U-DQ-11: 키워드는 바인드 값(%…%), ILIKE·ESCAPE, SQL 문자열 불변."""
    sql, params = compiled(area="서울", keyword="궁' OR 1=1 --")
    assert "OR 1=1" not in sql and "ILIKE" in sql and "ESCAPE" in sql
    assert "%궁' OR 1=1 --%" in params.values()


def test_type_and_sigungu():
    """U-DQ-12: 유형·시군구 조건 바인드."""
    sql, params = compiled(area="서울", content_type=12, sigungu_code="23")
    assert "content_type_id = " in sql and "sigungu_code = " in sql
    assert 12 in params.values() and "23" in params.values()


def test_on_date():
    """U-DQ-13: 행사 기간 조건."""
    sql, params = compiled(area="서울", on_date=date(2026, 11, 21))
    assert "event_start <=" in sql and "event_end >=" in sql and date(2026, 11, 21) in params.values()


def test_sort_modified():
    """U-DQ-14: 수정일순."""
    sql, _ = compiled(area="서울", sort="modified")
    assert "ORDER BY tour_items.modifiedtime DESC NULLS LAST, tour_items.contentid" in sql


def test_near_select():
    """U-DQ-15: 좌표 NOT NULL, 사각형 4조건, LIMIT 500."""
    sql, params = compiled(area="서울", near={"lat": 37.5663, "lng": 126.9779, "radius_km": 3})
    assert "lat IS NOT NULL" in sql and "lng IS NOT NULL" in sql
    assert sql.count("tour_items.lat >=") == 1 and sql.count("tour_items.lat <=") == 1
    assert sql.count("tour_items.lng >=") == 1 and sql.count("tour_items.lng <=") == 1
    assert 500 in params.values()


def test_haversine_city_hall_to_palace():
    """U-DQ-16: 서울시청 ↔ 경복궁 ≈ 1.48km."""
    assert haversine_km(37.5663, 126.9779, 37.5796, 126.9770) == pytest.approx(1.48, abs=0.02)


def test_haversine_seoul_jeju():
    """U-DQ-17: 서울 ↔ 제주시 ≈ 454km."""
    assert haversine_km(37.5665, 126.9780, 33.4996, 126.5312) == pytest.approx(454.0, abs=1.0)


def test_haversine_same_point():
    """U-DQ-18: 같은 점 → 0."""
    assert haversine_km(37.5, 127.0, 37.5, 127.0) == 0.0


def test_bounding_box():
    """U-DQ-19: 경복궁은 상자 안, (37.62, 126.98)은 밖."""
    min_lat, max_lat, min_lng, max_lng = bounding_box(37.5663, 126.9779, 3)
    assert min_lat <= 37.5796 <= max_lat and min_lng <= 126.9770 <= max_lng
    assert not (min_lat <= 37.62 <= max_lat)


def _rows():
    """기준점에서 대략 0.5·2.9·3.1km 북쪽 행 + 좌표 없는 행(입력 순서: 3.1, 0.5, 2.9, 없음)."""
    base_lat, base_lng = 37.5, 127.0
    per_km = 1 / 111.195  # 위도 1km
    return [
        {"contentid": "c31", "lat": base_lat + 3.1 * per_km, "lng": base_lng},
        {"contentid": "c05", "lat": base_lat + 0.5 * per_km, "lng": base_lng},
        {"contentid": "c29", "lat": base_lat + 2.9 * per_km, "lng": base_lng},
        {"contentid": "none", "lat": None, "lng": None},
    ]


def test_apply_near_sorted():
    """U-DQ-20: 반경 3km 안 2개, 거리 오름차순, 소수 2자리."""
    out = apply_near(_rows(), NearPoint(lat=37.5, lng=127.0, radius_km=3), True, 10)
    assert [r["contentid"] for r in out] == ["c05", "c29"]
    assert [r["distance_km"] for r in out] == [0.5, 2.9]


def test_apply_near_keep_order():
    """U-DQ-21: 거리순 아님 + limit 1 → 입력 순서 첫 번째(반경 안)."""
    out = apply_near(_rows(), NearPoint(lat=37.5, lng=127.0, radius_km=3), False, 1)
    assert [r["contentid"] for r in out] == ["c05"]


def test_row_to_item():
    """U-DQ-22: 키 = 항목 컬럼 + source, extra 없음, 날짜 ISO."""
    row = {c: None for c in ITEM_COLUMNS}
    row.update(contentid="1", title="t", as_of=date(2026, 11, 21), extra={"x": 1})
    item = row_to_item(row)
    assert set(item) == set(ITEM_COLUMNS) | {"source"}
    assert item["as_of"] == "2026-11-21" and "extra" not in item
