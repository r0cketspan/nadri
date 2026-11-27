"""data_query 툴 — tour_items 정형 조회(지역·시군구·유형·키워드·주변·행사일)."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import SQLAlchemyError

from nadri.core.models.tour import TourItem
from nadri.ingest.wiki.render import SOURCE_LABEL

if TYPE_CHECKING:
    from nadri.tools.server import ToolDeps

log = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0088
MAX_LIMIT = 20
NEAR_SQL_LIMIT = 500  # 주변 검색 1차 후보 안전 상한
# 결과 항목에 넣는 컬럼(extra는 서술 정보라 rag_query 몫)
ITEM_COLUMNS = (
    "contentid", "title", "content_type_id", "area", "sigungu_code", "addr", "lat", "lng",
    "tel", "usetime", "fee", "restdate", "event_start", "event_end", "as_of",
)


class NearPoint(BaseModel):
    """주변 검색 기준점."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=3.0, gt=0, le=20)


class DataQueryParams(BaseModel):
    """data_query 입력. LLM이 채우는 값이라 엄격히 검증한다."""

    area: Literal["서울", "제주"]
    sigungu_code: str | None = Field(default=None, pattern=r"^\d{1,5}$")
    content_type: Literal[12, 14, 15, 25, 28, 32, 38, 39] | None = None
    keyword: str | None = Field(default=None, max_length=50)
    near: NearPoint | None = None
    on_date: date | None = None
    sort: Literal["title", "distance", "modified"] = "title"
    limit: int = Field(default=10, ge=1)

    @field_validator("keyword")
    @classmethod
    def _blank_keyword(cls, v: str | None) -> str | None:
        """공백만 있는 키워드는 조건 없음(None)으로 본다."""
        return v.strip() or None if v is not None else None

    @field_validator("limit")
    @classmethod
    def _cap_limit(cls, v: int) -> int:
        """20 초과는 20으로 낮춘다(오류 대신)."""
        return min(v, MAX_LIMIT)

    @model_validator(mode="after")
    def _distance_needs_near(self) -> DataQueryParams:
        """거리순 정렬은 기준점이 있어야 한다."""
        if self.sort == "distance" and self.near is None:
            raise ValueError("sort=distance 는 near 가 필요합니다")
        return self


def escape_like(s: str) -> str:
    """
    LIKE 와일드카드를 이스케이프한다.

    Args:
        s: 사용자 키워드

    Returns:
        \\ → \\\\, % → \\%, _ → \\_ 로 바꾼 문자열(ESCAPE '\\'와 함께 사용)
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    두 좌표 사이 대원 거리.

    Returns:
        km (지구 반지름 6371.0088)
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """
    반경을 덮는 사각형 — SQL 1차 거르기용(정확한 거리는 apply_near에서).

    Returns:
        (min_lat, max_lat, min_lng, max_lng)
    """
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    dlng = dlat / max(math.cos(math.radians(lat)), 1e-6)
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def build_select(p: DataQueryParams) -> Select:
    """
    검증된 파라미터로 SQLAlchemy Select를 만든다. 모든 값은 바인드 파라미터(문자열 SQL 조립 없음).

    Args:
        p: 검증된 입력

    Returns:
        ITEM_COLUMNS를 고르는 Select
    """
    t = TourItem
    # 1) 기본 조건: 삭제 안 된 해당 지역
    stmt = select(*(getattr(t, c) for c in ITEM_COLUMNS)).where(t.deleted_at.is_(None), t.area == p.area)
    # 2) 같음 조건·키워드(제목·주소 부분 일치)
    if p.sigungu_code is not None:
        stmt = stmt.where(t.sigungu_code == p.sigungu_code)
    if p.content_type is not None:
        stmt = stmt.where(t.content_type_id == p.content_type)
    if p.keyword:
        kw = f"%{escape_like(p.keyword)}%"
        stmt = stmt.where(or_(t.title.ilike(kw, escape="\\"), t.addr.ilike(kw, escape="\\")))
    # 3) 행사일: 그날 진행 중인 행사만(기간 없는 행은 제외)
    if p.on_date is not None:
        stmt = stmt.where(t.event_start <= p.on_date, t.event_end >= p.on_date)
    # 4) 정렬
    if p.sort == "modified":
        stmt = stmt.order_by(t.modifiedtime.desc().nulls_last(), t.contentid)
    else:
        stmt = stmt.order_by(t.title, t.contentid)
    # 5) 주변 검색: 좌표 있는 행 + 사각형, 넉넉히 가져와 Python에서 거리 계산
    if p.near is not None:
        min_lat, max_lat, min_lng, max_lng = bounding_box(p.near.lat, p.near.lng, p.near.radius_km)
        stmt = stmt.where(
            t.lat.is_not(None), t.lng.is_not(None),
            t.lat >= min_lat, t.lat <= max_lat, t.lng >= min_lng, t.lng <= max_lng,
        )
        return stmt.limit(NEAR_SQL_LIMIT)
    return stmt.limit(p.limit)


def apply_near(rows: list[dict], near: NearPoint, sort_by_distance: bool, limit: int) -> list[dict]:
    """
    거리 계산·반경 필터·(선택) 거리순 정렬 후 limit개로 자른다.

    Args:
        rows: build_select 결과 행(dict)
        near: 기준점·반경
        sort_by_distance: True면 거리 오름차순
        limit: 최대 개수

    Returns:
        distance_km(소수 2자리)가 붙은 행 목록
    """
    # 1) 좌표 없는 행은 빼고 거리 계산 → 반경 안만 남긴다
    kept = []
    for row in rows:
        if row.get("lat") is None or row.get("lng") is None:
            continue
        d = haversine_km(near.lat, near.lng, row["lat"], row["lng"])
        if d <= near.radius_km:
            kept.append({**row, "distance_km": round(d, 2)})
    # 2) 거리순이면 정렬(안정 정렬), 아니면 SQL 순서 유지
    if sort_by_distance:
        kept.sort(key=lambda r: r["distance_km"])
    return kept[:limit]


def row_to_item(row: Mapping[str, Any]) -> dict:
    """
    DB 행을 툴 결과 항목(dict)으로 바꾼다.

    Returns:
        ITEM_COLUMNS(+distance_km) + source. 날짜는 ISO 문자열, extra는 넣지 않음
    """
    item = {}
    for c in (*ITEM_COLUMNS, "distance_km"):
        if c not in row:
            continue
        v = row[c]
        item[c] = v.isoformat() if isinstance(v, date) else v
    item["source"] = SOURCE_LABEL
    return item


async def data_query(p: DataQueryParams, deps: ToolDeps) -> dict:
    """
    tour_items를 조건으로 조회해 항목 목록을 돌려준다.

    Args:
        p: 검증된 입력
        deps: 공유 자원(nadri_tools 세션)

    Returns:
        {"items": [...], "count": n}

    Raises:
        RuntimeError: DB 오류(한국어 짧은 메시지)
    """
    t0 = time.monotonic()
    # 1) 조회
    try:
        async with deps.sf() as s:
            rows = [dict(r) for r in (await s.execute(build_select(p))).mappings().all()]
    except SQLAlchemyError:
        log.exception("tool=data_query db_error")
        raise RuntimeError("관광 정보를 조회할 수 없습니다") from None
    # 2) 주변 검색이면 거리 필터·정렬
    if p.near is not None:
        rows = apply_near(rows, p.near, p.sort == "distance", p.limit)
    items = [row_to_item(r) for r in rows]
    # 3) 로그 한 줄(인자 원문 없음)
    log.info("tool=data_query ms=%d count=%d", (time.monotonic() - t0) * 1000, len(items))
    return {"items": items, "count": len(items)}
