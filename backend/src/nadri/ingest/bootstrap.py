"""소량 적재(bootstrap)·재인덱싱(reindex)·totalCount 측정(count)과 TourAPI 호출 수 기록.

01은 예산을 '실행 전 점검'만 한다(강제 예산·이어하기는 03).
"""

import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Literal

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nadri.core.config import Settings
from nadri.core.models.ingest import IngestRun, IngestState
from nadri.core.models.tour import TourItem, WikiPage
from nadri.core.tourapi import AREAS, KST, TourApiClient, TourApiError
from nadri.ingest.indexer import LightRagClient, PageToIndex, apply_outcomes, index_pages
from nadri.ingest.raw import save_raw
from nadri.ingest.upsert import build_record, upsert_tour_item
from nadri.ingest.wiki.render import content_hash, entity_path, render_entity, write_page

MAX_LIMIT = 50  # 01 소량 적재 상한
SUPPORTED_TYPES = {12}  # 01 템플릿은 관광지만(다른 유형은 03)


@dataclass
class BootstrapResult:
    """한 번의 적재 실행 요약(ingest_runs.stats에 그대로 저장)."""

    run_id: int
    calls: int = 0
    listed: int = 0
    upserted: dict[str, int] = field(default_factory=lambda: {"inserted": 0, "updated": 0, "unchanged": 0})
    pages_written: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    index_elapsed_s: float = 0.0
    elapsed_s: float = 0.0
    errors: list[str] = field(default_factory=list)  # "contentid: 사유"


def estimate_calls(limit: int) -> int:
    """
    이번 실행 예상 호출 수.

    Args:
        limit: 적재 건수

    Returns:
        목록 1 + 상세 3 × limit
    """
    return 1 + 3 * limit


def budget_allows(used_today: int, estimated: int, budget: int) -> bool:
    """
    오늘 ingest 사용량 + 예상 호출 ≤ 예산이면 True. (01의 최소 점검 — 강제 예산은 03)

    Args:
        used_today: 오늘 ingest 호출 수
        estimated: 이번 실행 예상 호출 수
        budget: 하루 ingest 예산(기본 800)
    """
    return used_today + estimated <= budget


def validate_args(area: str, content_type_id: int, limit: int) -> None:
    """
    bootstrap 인자를 검사한다.

    Args:
        area: 지역 이름(AREAS 키)
        content_type_id: 관광 유형(01은 12만)
        limit: 적재 건수(1~50)

    Raises:
        ValueError: 어긋나면 한국어 사유와 함께
    """
    if area not in AREAS:
        raise ValueError(f"지원하지 않는 지역입니다: {area} (가능: {', '.join(AREAS)})")
    if content_type_id not in SUPPORTED_TYPES:
        raise ValueError(f"01 단계는 관광지(12)만 적재합니다: {content_type_id}")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit은 1~{MAX_LIMIT} 사이여야 합니다: {limit}")


def estimate_days(totals: dict[tuple[str, int], int], budget: int, rows_per_list_call: int = 100) -> dict[str, int]:
    """
    totalCount 표로 전체 적재 일수를 두 가지로 추정한다(spec §9 식).

    Args:
        totals: (지역, 유형) → totalCount
        budget: 하루 예산
        rows_per_list_call: 목록 1회 건수

    Returns:
        {"service_wide": 서비스 전체 한도일 때, "per_operation": 오퍼레이션별 한도일 때}
    """
    # 1) 서비스 전체 한도: 목록 호출 + 상세 3종 호출을 모두 같은 예산에서 쓴다
    list_calls = sum(math.ceil(t / rows_per_list_call) for t in totals.values())
    total = sum(totals.values())
    service_wide = math.ceil((list_calls + 3 * total) / budget)
    # 2) 오퍼레이션별 한도: 상세 오퍼레이션 하나가 병목
    per_operation = math.ceil(total / budget)
    return {"service_wide": service_wide, "per_operation": per_operation}


def _calls_key(day: date) -> str:
    """ingest_state 호출 수 카운터 키."""
    return f"tourapi_calls:{day.isoformat()}"


async def record_call(sf: async_sessionmaker[AsyncSession], day: date, kind: Literal["ingest"] = "ingest") -> None:
    """
    ingest_state 'tourapi_calls:{day}'의 kind 카운터를 원자적으로 +1 한다.

    Args:
        sf: 세션 팩토리(nadri_app)
        day: KST 날짜
        kind: 카운터 종류(01은 ingest만, live는 10)

    Side effects:
        한 문장(INSERT … ON CONFLICT … jsonb_set)으로 갱신하고 바로 커밋한다.
    """
    # 1) 키가 없으면 {"ingest": 0, "live": 0}에 kind만 1로 넣고, 있으면 kind 값만 +1 한다(한 문장이라 원자적)
    stmt = text(
        """
        INSERT INTO ingest_state (key, value)
        VALUES (:key, jsonb_build_object('ingest', 0, 'live', 0) || jsonb_build_object(CAST(:kind AS text), 1))
        ON CONFLICT (key) DO UPDATE
        SET value = jsonb_set(
            ingest_state.value, ARRAY[CAST(:kind AS text)],
            to_jsonb(COALESCE((ingest_state.value ->> CAST(:kind AS text))::int, 0) + 1)
        )
        """
    )
    async with sf() as s:
        await s.execute(stmt, {"key": _calls_key(day), "kind": kind})
        await s.commit()


async def calls_today(sf: async_sessionmaker[AsyncSession], day: date) -> dict[str, int]:
    """
    그날의 TourAPI 호출 수를 돌려준다.

    Returns:
        {"ingest": n, "live": n} — 기록이 없으면 0
    """
    async with sf() as s:
        value = await s.scalar(select(IngestState.value).where(IngestState.key == _calls_key(day)))
    value = value or {}
    return {"ingest": int(value.get("ingest", 0)), "live": int(value.get("live", 0))}


def make_call_recorder(sf: async_sessionmaker[AsyncSession]) -> Callable[[str], Awaitable[None]]:
    """TourApiClient(on_call=…)에 넣을 콜백 — 호출 시각의 KST 날짜로 카운터를 올린다."""

    async def on_call(operation: str) -> None:
        """호출 1회를 오늘(KST) ingest 카운터에 더한다."""
        await record_call(sf, datetime.now(KST).date())

    return on_call


async def _start_run(sf: async_sessionmaker[AsyncSession], kind: str) -> int:
    """ingest_runs에 running 행을 만들고 id를 돌려준다."""
    async with sf() as s:
        run = IngestRun(kind=kind, status="running")
        s.add(run)
        await s.commit()
        return run.id


async def _finish_run(
    sf: async_sessionmaker[AsyncSession], result: BootstrapResult, status: str, error: str | None = None
) -> None:
    """ingest_runs 행에 종료 시각·결과·통계를 적는다."""
    async with sf() as s:
        await s.execute(
            update(IngestRun)
            .where(IngestRun.id == result.run_id)
            .values(finished_at=func.now(), status=status, stats=asdict(result), error=error)
        )
        await s.commit()


async def _register_page(s: AsyncSession, item: TourItem, wiki_dir) -> PageToIndex:
    """
    항목을 렌더해 파일로 쓰고 wiki_pages 메타를 upsert한 뒤 인덱싱 후보를 돌려준다.

    Args:
        s: 열린 세션(커밋은 호출부)
        item: DB에서 읽은 관광 항목
        wiki_dir: 위키 폴더

    Returns:
        PageToIndex — old_hash·old_doc_id는 갱신 전 wiki_pages 값
    """
    # 1) 렌더·해시·원자적 파일 쓰기
    path = entity_path(item.content_type_id, item.contentid)
    page_text = render_entity(item)
    write_page(wiki_dir, path, page_text)

    # 2) 메타만 upsert(해시·doc_id는 인덱싱 성공 후에만) — RETURNING으로 이전 해시·doc_id를 받는다
    meta = dict(
        kind="entity", contentid=item.contentid, title=item.title,
        area=item.area, sigungu_code=item.sigungu_code, as_of=item.as_of,
    )
    stmt = insert(WikiPage).values(path=path, **meta)
    stmt = stmt.on_conflict_do_update(index_elements=["path"], set_=meta).returning(
        WikiPage.content_hash, WikiPage.lightrag_doc_id
    )
    old = (await s.execute(stmt)).one()
    return PageToIndex(path, page_text, content_hash(page_text), old.content_hash, old.lightrag_doc_id)


async def _index_and_apply(
    pages: list[PageToIndex], result: BootstrapResult, settings: Settings,
    sf: async_sessionmaker[AsyncSession], lightrag: LightRagClient,
) -> None:
    """바뀐 페이지를 인덱싱하고 결과를 wiki_pages·요약에 반영한다."""
    t0 = time.monotonic()
    outcomes = await index_pages(lightrag, pages, timeout_s=settings.index_timeout_s)
    result.index_elapsed_s = round(time.monotonic() - t0, 2)
    async with sf() as s:
        await apply_outcomes(s, outcomes)
        await s.commit()
    for o in outcomes:
        if o.status == "indexed":
            result.indexed += 1
        elif o.status == "skipped":
            result.skipped += 1
        else:
            result.failed += 1
            result.errors.append(f"{o.path}: {o.reason}")


async def _load_item(s: AsyncSession, contentid: str) -> TourItem:
    """DB의 최신 값(updated_at 포함)으로 항목을 읽는다."""
    stmt = select(TourItem).where(TourItem.contentid == contentid).execution_options(populate_existing=True)
    return (await s.execute(stmt)).scalar_one()


async def run_bootstrap(
    area: str, content_type_id: int, limit: int, *, settings: Settings,
    sf: async_sessionmaker[AsyncSession], tourapi: TourApiClient, lightrag: LightRagClient,
) -> BootstrapResult:
    """
    목록 1페이지(limit건) → 건별 상세 3종 → raw → upsert → 렌더·파일 → wiki_pages → 바뀐 페이지 인덱싱.

    Args:
        area, content_type_id, limit: 적재 대상(validate_args 규칙)
        settings: 설정(폴더·예산·인덱싱 상한)
        sf: 세션 팩토리(nadri_app)
        tourapi: on_call로 호출 수를 기록하는 클라이언트
        lightrag: LightRAG 클라이언트

    Returns:
        실행 요약(ingest_runs.stats와 같음)

    Raises:
        ValueError: 인자 오류(호출 없음)
        SystemExit(3): 오늘 예산으로 부족해 시작하지 않음
        Exception: 목록 호출 실패 등 — ingest_runs에 failed로 기록한 뒤 다시 던짐
    """
    t_start = time.monotonic()
    # 1) 인자 검증
    validate_args(area, content_type_id, limit)

    # 2) 예산 점검 — 부족하면 시작하지 않는다
    used = (await calls_today(sf, datetime.now(KST).date()))["ingest"]
    if not budget_allows(used, estimate_calls(limit), settings.tourapi_daily_ingest_budget):
        print(f"오늘 TourAPI 사용량 {used} + 예상 {estimate_calls(limit)} 이 예산 {settings.tourapi_daily_ingest_budget}을 넘어 시작하지 않습니다.")
        raise SystemExit(3)

    # 3) 실행 기록 시작
    result = BootstrapResult(run_id=await _start_run(sf, "bootstrap"))
    calls_before = tourapi.calls
    aborted = False
    try:
        # 4) 목록 1페이지 → raw
        listing = await tourapi.area_based_list(area, content_type_id, num_of_rows=limit)
        save_raw(settings.raw_dir, listing, f"{area}_{content_type_id}_p1")
        result.listed = len(listing.items)

        # 5) 항목마다 상세 3종 → raw → upsert → 렌더·파일·wiki_pages
        pages: list[PageToIndex] = []
        for i, row in enumerate(listing.items[:limit], start=1):
            cid = str(row.get("contentid", "")).strip()
            try:
                common = await tourapi.detail_common(cid)
                intro = await tourapi.detail_intro(cid, content_type_id)
                info = await tourapi.detail_info(cid, content_type_id)
                for resp in (common, intro, info):
                    save_raw(settings.raw_dir, resp, cid)
                if not common.items:
                    raise ValueError("detailCommon2 결과 없음")
                rec = build_record(area, common.items[0], intro.items[0] if intro.items else {}, info.items, common.fetched_at)
                async with sf() as s:
                    kind = await upsert_tour_item(s, rec)
                    await s.commit()
                    pages.append(await _register_page(s, await _load_item(s, rec.contentid), settings.wiki_dir))
                    await s.commit()
                result.upserted[kind] += 1
                result.pages_written += 1
                print(f"[{i}/{len(listing.items)}] {cid} {rec.title} {kind}", flush=True)
            except TourApiError as e:
                result.errors.append(f"{cid}: {e}")
                # 한도 초과는 남은 항목을 멈추고, 받은 것만 인덱싱한다
                if e.quota_exceeded or e.rate_limited:
                    aborted = True
                    break
            except (KeyError, ValueError, TypeError) as e:
                result.errors.append(f"{cid}: 매핑 오류 {type(e).__name__}: {e}")

        # 6) 바뀐 페이지만 인덱싱 → wiki_pages 반영
        await _index_and_apply(pages, result, settings, sf, lightrag)
    except Exception as e:
        # 7-a) 예외 — 기록 후 다시 던진다(메시지에 비밀값 없음)
        result.calls = tourapi.calls - calls_before
        result.elapsed_s = round(time.monotonic() - t_start, 2)
        await _finish_run(sf, result, "failed", error=str(e))
        raise

    # 7-b) 종료 기록 — 한도 중단·인덱싱 실패가 있으면 failed
    result.calls = tourapi.calls - calls_before
    result.elapsed_s = round(time.monotonic() - t_start, 2)
    status = "failed" if aborted or result.failed else "done"
    await _finish_run(sf, result, status, error="TourAPI 한도 초과로 중단" if aborted else None)
    return result


async def run_reindex(
    contentids: list[str] | None, *, settings: Settings,
    sf: async_sessionmaker[AsyncSession], lightrag: LightRagClient,
) -> BootstrapResult:
    """
    TourAPI 없이 tour_items에서 다시 렌더해 바뀐 페이지만 인덱싱한다(A16 확인용).

    Args:
        contentids: 대상 관광지 ID 목록(None이면 삭제되지 않은 전체)
        settings, sf, lightrag: run_bootstrap과 같음

    Returns:
        실행 요약(calls=0)
    """
    t_start = time.monotonic()
    result = BootstrapResult(run_id=await _start_run(sf, "reindex"))
    try:
        # 1) 대상 항목을 읽어 렌더·파일·wiki_pages 메타 갱신
        async with sf() as s:
            stmt = select(TourItem).where(TourItem.deleted_at.is_(None)).order_by(TourItem.contentid)
            if contentids:
                stmt = stmt.where(TourItem.contentid.in_(contentids))
            items = (await s.execute(stmt)).scalars().all()
            pages = [await _register_page(s, item, settings.wiki_dir) for item in items]
            await s.commit()
        result.listed = len(items)
        result.pages_written = len(pages)
        # 2) 바뀐 페이지만 인덱싱
        await _index_and_apply(pages, result, settings, sf, lightrag)
    except Exception as e:
        result.elapsed_s = round(time.monotonic() - t_start, 2)
        await _finish_run(sf, result, "failed", error=str(e))
        raise
    result.elapsed_s = round(time.monotonic() - t_start, 2)
    await _finish_run(sf, result, "failed" if result.failed else "done")
    return result


async def count_totals(tourapi: TourApiClient, areas: list[str], types: list[int]) -> dict[tuple[str, int], int]:
    """
    지역×유형별 totalCount를 numOfRows=1 목록 호출로 센다(서울·제주 × 8종 = 16호출).

    count는 raw를 저장하지 않는다(측정용 호출). 호출 수는 클라이언트 on_call로 기록된다.

    Returns:
        (지역, 유형) → totalCount
    """
    totals = {}
    for area in areas:
        for t in types:
            totals[(area, t)] = (await tourapi.area_based_list(area, t, num_of_rows=1)).total_count
    return totals
