"""TourAPI 상세 응답 → TourItemRecord 변환과 tour_items upsert."""

import html
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Literal

from sqlalchemy import func, literal_column, or_, tuple_
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from nadri.core.models.tour import TourItem
from nadri.core.tourapi import KST

# 내용이 바뀌었는지 비교하는 컬럼 — detail_synced_at은 빼서 같은 날 재실행이 시각 차이만으로 갱신되지 않게 한다
COMPARE_COLUMNS = (
    "content_type_id", "area", "sigungu_code", "title", "addr", "lat", "lng", "tel",
    "usetime", "fee", "restdate", "event_start", "event_end", "extra", "modifiedtime", "as_of",
)
# intro 중 정식 컬럼으로 옮긴 필드(나머지는 extra.intro로)
_INTRO_MAPPED = {"contentid", "contenttypeid", "usetime", "restdate"}
_FEE_NAMES = ("입장료", "이용요금")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_MANY_NL = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class TourItemRecord:
    """tour_items 한 행에 넣을 값(updated_at·deleted_at 제외)."""

    contentid: str
    content_type_id: int
    area: str
    sigungu_code: str | None
    title: str
    addr: str | None
    lat: float | None
    lng: float | None
    tel: str | None
    usetime: str | None
    fee: str | None
    restdate: str | None
    event_start: date | None
    event_end: date | None
    extra: dict
    modifiedtime: datetime | None
    detail_synced_at: datetime
    as_of: date


def clean_text(value: str | None) -> str | None:
    """
    TourAPI 문자열의 HTML을 정리한다.

    Args:
        value: 원문(HTML 태그·엔티티가 섞일 수 있음)

    Returns:
        <br> → 줄바꿈, 다른 태그 제거, 엔티티 해제, 줄마다 앞뒤 공백 제거한 문자열. 비면 None
    """
    # 1) 값이 없으면 None
    if value is None:
        return None
    # 2) 줄바꿈 태그를 실제 줄바꿈으로, 나머지 태그는 지운다(링크는 글자만 남음)
    text = _TAG.sub("", _BR.sub("\n", str(value)))
    # 3) &amp; 같은 엔티티를 해제하고 줄마다 공백을 정리한다
    text = "\n".join(line.strip() for line in html.unescape(text).splitlines())
    # 4) 빈 줄이 여러 개면 하나로 줄이고, 결과가 비면 None
    text = _MANY_NL.sub("\n\n", text).strip()
    return text or None


def _to_float(value: object) -> float | None:
    """좌표 문자열을 float로. 빈 값·0·해석 불가면 None."""
    try:
        f = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return f if f != 0 else None


def _parse_modifiedtime(value: object) -> datetime | None:
    """'YYYYMMDDHHMMSS'(KST)를 tz-aware datetime으로. 형식이 다르면 None."""
    try:
        return datetime.strptime(str(value), "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except (TypeError, ValueError):
        return None


def build_record(area: str, common: dict, intro: dict, info: list[dict], fetched_at: datetime) -> TourItemRecord:
    """
    detailCommon2·detailIntro2·detailInfo2 item을 TourItemRecord로 바꾼다(순수 함수, 타입 12 기준).

    Args:
        area: '서울' 또는 '제주'
        common: detailCommon2 item
        intro: detailIntro2 item(없으면 빈 dict)
        info: detailInfo2 item 목록
        fetched_at: 상세를 받은 시각(tz-aware)

    Returns:
        upsert에 쓸 레코드

    Raises:
        KeyError/ValueError: contentid·contenttypeid·title이 없거나 잘못됐을 때(호출부가 항목 오류로 기록)
    """
    # 1) 주소: addr1 + addr2를 공백 하나로 잇는다
    addr = clean_text(" ".join(p for p in (clean_text(common.get("addr1")), clean_text(common.get("addr2"))) if p))

    # 2) info 목록: 이름/값을 정리하고, 요금은 이름에 '입장료'·'이용요금'이 든 첫 항목
    info_items = []
    fee = None
    for row in info:
        name, text_ = clean_text(row.get("infoname")), clean_text(row.get("infotext"))
        if not name or not text_:
            continue
        info_items.append({"name": name, "text": text_})
        if fee is None and any(k in name.replace(" ", "") for k in _FEE_NAMES):
            fee = text_

    # 3) intro 중 컬럼으로 옮기지 않은 필드는 extra.intro로(빈 값 제외, 키 정렬로 결정적)
    intro_rest = {}
    for k in sorted(intro):
        if k in _INTRO_MAPPED:
            continue
        v = clean_text(intro[k])
        if v:
            intro_rest[k] = v

    # 4) extra: 빈 값 키는 넣지 않는다
    extra = {
        "overview": clean_text(common.get("overview")),
        "homepage": clean_text(common.get("homepage")),
        "intro": intro_rest,
        "info": info_items,
    }
    extra = {k: v for k, v in extra.items() if v}

    # 5) 레코드 조립 — 전화는 common, 없으면 intro의 문의처
    return TourItemRecord(
        contentid=str(common["contentid"]).strip(),
        content_type_id=int(common["contenttypeid"]),
        area=area,
        sigungu_code=clean_text(common.get("sigungucode")),
        title=clean_text(common["title"]) or "",
        addr=addr,
        lat=_to_float(common.get("mapy")),
        lng=_to_float(common.get("mapx")),
        tel=clean_text(common.get("tel")) or clean_text(intro.get("infocenter")),
        usetime=clean_text(intro.get("usetime")),
        fee=fee,
        restdate=clean_text(intro.get("restdate")),
        event_start=None,
        event_end=None,
        extra=extra,
        modifiedtime=_parse_modifiedtime(common.get("modifiedtime")),
        detail_synced_at=fetched_at,
        as_of=fetched_at.astimezone(KST).date(),
    )


def build_upsert_stmt(rec: TourItemRecord) -> Insert:
    """
    INSERT … ON CONFLICT (contentid) DO UPDATE … WHERE 값이 달라졌을 때만, RETURNING (xmax = 0) 문을 만든다.

    Args:
        rec: 넣을 레코드

    Returns:
        실행 시 새 행이면 inserted=True, 갱신이면 False 한 행, 내용이 같으면 행 없음을 돌려주는 문
    """
    table = TourItem.__table__
    # 1) 기본 INSERT — 모든 값은 바인드 파라미터
    stmt = insert(table).values(**asdict(rec))
    excluded = stmt.excluded

    # 2) 충돌 시 갱신할 값: 비교 컬럼 + 수집 시각, updated_at은 now(), 삭제 표시는 해제
    set_ = {c: excluded[c] for c in COMPARE_COLUMNS}
    set_.update(detail_synced_at=excluded.detail_synced_at, updated_at=func.now(), deleted_at=None)

    # 3) 내용이 같고 삭제 표시도 없으면 건드리지 않는다(updated_at 유지 → 페이지도 그대로)
    changed = or_(
        tuple_(*(table.c[c] for c in COMPARE_COLUMNS)).is_distinct_from(
            tuple_(*(excluded[c] for c in COMPARE_COLUMNS))
        ),
        table.c.deleted_at.is_not(None),
    )
    stmt = stmt.on_conflict_do_update(index_elements=["contentid"], set_=set_, where=changed)

    # 4) xmax = 0 이면 새로 넣은 행(갱신 행은 xmax가 0이 아님)
    return stmt.returning(literal_column("(xmax = 0)").label("inserted"))


async def upsert_tour_item(session: AsyncSession, rec: TourItemRecord) -> Literal["inserted", "updated", "unchanged"]:
    """
    한 건을 upsert하고 결과 종류를 돌려준다. 내용이 같으면 행을 건드리지 않는다(updated_at 유지).

    Args:
        session: 열린 세션(커밋은 호출부)
        rec: 넣을 레코드

    Returns:
        'inserted' / 'updated' / 'unchanged'
    """
    # 1) 문 실행 → RETURNING 행이 없으면 WHERE에서 걸러진 것(변경 없음)
    row = (await session.execute(build_upsert_stmt(rec))).first()
    if row is None:
        return "unchanged"
    # 2) xmax로 신규/갱신 구분
    return "inserted" if row.inserted else "updated"
