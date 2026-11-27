"""nadri 명령줄 — 적재(ingest)·툴 점검(tools)·LightRAG 표본(lightrag).

종료 코드: 성공 0, 실행 실패 1, 설정·인자 오류 2, 예산 초과로 시작 안 함 3.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime

import httpx
from pydantic import ValidationError

from nadri.core.config import Settings, get_settings, require
from nadri.core.db import create_engine, session_factory
from nadri.core.tourapi import AREAS, CONTENT_TYPES, KST, TourApiClient, TourApiError
from nadri.ingest import bootstrap as bs
from nadri.ingest.indexer import LightRagClient


def _tourapi(settings: Settings, sf) -> TourApiClient:
    """호출 수를 ingest_state에 기록하는 TourAPI 클라이언트를 만든다."""
    return TourApiClient(
        require(settings.tourapi_service_key, "TOURAPI_SERVICE_KEY"),
        settings.tourapi_base_url,
        timeout=settings.tourapi_timeout_s,
        on_call=bs.make_call_recorder(sf),
    )


def _lightrag(settings: Settings) -> LightRagClient:
    """LightRAG 문서 API 클라이언트를 만든다."""
    return LightRagClient(settings.lightrag_url, require(settings.lightrag_api_key, "LIGHTRAG_API_KEY"))


def _print_json(data: dict) -> None:
    """요약 JSON을 한글 그대로 출력한다."""
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


async def cmd_bootstrap(args: argparse.Namespace, settings: Settings) -> int:
    """`nadri ingest bootstrap` — 소량 적재 후 요약 JSON 출력."""
    # 1) 인자 검사(호출 전)
    try:
        bs.validate_args(args.area, args.type, args.limit)
    except ValueError as e:
        print(f"인자 오류: {e}", file=sys.stderr)
        return 2
    # 2) 클라이언트 준비 → 실행 → 요약
    engine = create_engine(settings)
    sf = session_factory(engine)
    tourapi, lightrag = _tourapi(settings, sf), _lightrag(settings)
    try:
        result = await bs.run_bootstrap(
            args.area, args.type, args.limit, settings=settings, sf=sf, tourapi=tourapi, lightrag=lightrag
        )
        _print_json(asdict(result))
        return 1 if result.failed or result.errors else 0
    except TourApiError as e:
        print(f"TourAPI 실패: {e}", file=sys.stderr)
        return 1
    finally:
        await tourapi.aclose()
        await lightrag.aclose()
        await engine.dispose()


async def cmd_reindex(args: argparse.Namespace, settings: Settings) -> int:
    """`nadri ingest reindex` — TourAPI 없이 다시 렌더·인덱싱, LightRAG 문서 수 전후 출력."""
    engine = create_engine(settings)
    sf = session_factory(engine)
    lightrag = _lightrag(settings)
    try:
        # 1) 전후 문서 수로 delete→insert가 중복을 남기지 않는지 본다(A16)
        before = await lightrag.count_documents()
        result = await bs.run_reindex(args.contentid or None, settings=settings, sf=sf, lightrag=lightrag)
        after = await lightrag.count_documents()
        _print_json({**asdict(result), "documents_before": before, "documents_after": after})
        return 1 if result.failed else 0
    finally:
        await lightrag.aclose()
        await engine.dispose()


async def cmd_count(args: argparse.Namespace, settings: Settings) -> int:
    """`nadri ingest count` — 서울·제주 × 8종 totalCount 표와 적재 일수 추정(16호출)."""
    engine = create_engine(settings)
    sf = session_factory(engine)
    tourapi = _tourapi(settings, sf)
    try:
        # 1) 예산 점검(16호출)
        n_calls = len(AREAS) * len(CONTENT_TYPES)
        used = (await bs.calls_today(sf, datetime.now(KST).date()))["ingest"]
        if not bs.budget_allows(used, n_calls, settings.tourapi_daily_ingest_budget):
            print(f"오늘 사용량 {used} + {n_calls} 이 예산을 넘어 시작하지 않습니다.", file=sys.stderr)
            return 3
        # 2) 집계 → 표 출력
        totals = await bs.count_totals(tourapi, list(AREAS), list(CONTENT_TYPES))
        print("유형\t" + "\t".join(AREAS))
        for t, name in CONTENT_TYPES.items():
            print(f"{t} {name}\t" + "\t".join(str(totals[(a, t)]) for a in AREAS))
        print(f"합계\t{sum(totals.values())}")
        days = bs.estimate_days(totals, settings.tourapi_daily_ingest_budget)
        print(f"적재 일수 — 서비스 전체 한도: {days['service_wide']}일 / 오퍼레이션별 한도: {days['per_operation']}일")
        return 0
    except TourApiError as e:
        print(f"TourAPI 실패: {e}", file=sys.stderr)
        return 1
    finally:
        await tourapi.aclose()
        await engine.dispose()


def _summary(result: object, limit: int = 300) -> str:
    """툴 결과를 한 줄 요약 문자열로."""
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


async def cmd_smoke(args: argparse.Namespace, settings: Settings) -> int:
    """`nadri tools smoke` — langchain-mcp-adapters로 툴 목록·3종 호출(A21), --repeat로 rag_query 지연(A9)."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    # 1) 어댑터로 툴 목록을 받는다(토큰은 headers로)
    token = require(settings.tools_api_key, "TOOLS_API_KEY")
    client = MultiServerMCPClient({
        "tour": {
            "transport": "streamable_http",
            "url": settings.tools_url,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    })
    tools = {t.name: t for t in await client.get_tools()}
    print("툴:", ", ".join(sorted(tools)))

    # 2) --repeat: rag_query만 N회, 첫 회(워밍업) 제외 p50·p95
    if args.repeat:
        ms = []
        for i in range(args.repeat):
            t0 = time.monotonic()
            await tools["rag_query"].ainvoke({"question": args.question})
            ms.append((time.monotonic() - t0) * 1000)
            print(f"[{i + 1}/{args.repeat}] rag_query {ms[-1]:.0f}ms")
        warm = ms[1:] or ms
        p95 = statistics.quantiles(warm, n=20)[-1] if len(warm) >= 2 else warm[0]
        print(f"p50={statistics.median(warm):.0f}ms p95={p95:.0f}ms (첫 회 제외 {len(warm)}회, 리랭크 시간은 tour-tools 로그 rerank_ms)")
        return 0

    # 3) 3종 각각 호출 — 이름·소요 ms·결과 요약
    calls = [
        ("rag_query", {"question": args.question}),
        ("data_query", {"area": "서울", "keyword": "궁", "limit": 5}),
        ("get_datetime", {}),
    ]
    ok = True
    for name, arg in calls:
        t0 = time.monotonic()
        try:
            result = await tools[name].ainvoke(arg)
            summary = _summary(result)
            # 어댑터는 툴 오류(isError)를 예외 대신 "Error executing tool …" 내용으로 돌려준다
            if "Error executing tool" in summary:
                ok = False
                print(f"{name} 실패 {(time.monotonic() - t0) * 1000:.0f}ms {summary}")
            else:
                print(f"{name} {(time.monotonic() - t0) * 1000:.0f}ms {summary}")
        except Exception as e:  # 툴 오류도 보고만 하고 다음 툴로
            ok = False
            print(f"{name} 실패: {type(e).__name__}: {e}")
    return 0 if ok else 1


async def cmd_sample(args: argparse.Namespace, settings: Settings) -> int:
    """`nadri lightrag sample` — /query/data의 엔티티·관계 상위 N개를 표로(A8 한국어 추출 품질 확인)."""
    key = require(settings.lightrag_api_key, "LIGHTRAG_API_KEY")
    async with httpx.AsyncClient(base_url=settings.lightrag_url, headers={"X-API-Key": key}, timeout=60) as http:
        resp = await http.post("/query/data", json={"query": args.query, "mode": "mix", "top_k": args.limit})
        resp.raise_for_status()
        data = resp.json().get("data") or {}
    # 1) 엔티티: 이름 · 유형 · 설명 앞부분 · 출처 파일
    print(f"## 엔티티 (상위 {args.limit})")
    for e in (data.get("entities") or [])[: args.limit]:
        desc = (e.get("description") or "").replace("\n", " ")[:80]
        print(f"- {e.get('entity_name')} | {e.get('entity_type')} | {desc} | {e.get('file_path')}")
    # 2) 관계: 출발 → 도착 · 설명 앞부분
    print(f"## 관계 (상위 {args.limit})")
    for r in (data.get("relationships") or [])[: args.limit]:
        desc = (r.get("description") or "").replace("\n", " ")[:80]
        print(f"- {r.get('src_id')} → {r.get('tgt_id')} | {desc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """하위 명령 구조를 만든다."""
    p = argparse.ArgumentParser(prog="nadri")
    top = p.add_subparsers(dest="group", required=True)

    ingest = top.add_parser("ingest", help="TourAPI 적재·재인덱싱").add_subparsers(dest="cmd", required=True)
    b = ingest.add_parser("bootstrap", help="지역·유형 소량 적재")
    b.add_argument("--area", required=True)
    b.add_argument("--type", type=int, default=12)
    b.add_argument("--limit", type=int, required=True)
    b.set_defaults(func=cmd_bootstrap)
    r = ingest.add_parser("reindex", help="tour_items에서 다시 렌더·바뀐 페이지만 인덱싱")
    r.add_argument("--contentid", nargs="*")
    r.set_defaults(func=cmd_reindex)
    ingest.add_parser("count", help="서울·제주 × 8종 totalCount").set_defaults(func=cmd_count)

    tools = top.add_parser("tools", help="MCP 툴 점검").add_subparsers(dest="cmd", required=True)
    s = tools.add_parser("smoke", help="어댑터로 툴 3종 호출")
    s.add_argument("--question", default="경복궁 관람 시간과 휴무일")
    s.add_argument("--repeat", type=int, default=0)
    s.set_defaults(func=cmd_smoke)

    lr = top.add_parser("lightrag", help="LightRAG 확인").add_subparsers(dest="cmd", required=True)
    sm = lr.add_parser("sample", help="엔티티·관계 표본")
    sm.add_argument("--query", required=True)
    sm.add_argument("--limit", type=int, default=20)
    sm.set_defaults(func=cmd_sample)
    return p


def main() -> None:
    """`nadri` 진입점 — 인자를 해석해 하위 명령을 asyncio로 실행하고 종료 코드로 끝낸다."""
    # 1) 인자 해석(argparse 오류는 종료 코드 2)
    args = build_parser().parse_args()
    # 2) 설정 읽기 — 필수 값(DB_USER 등)이 없으면 2
    try:
        settings = get_settings()
    except ValidationError as e:
        # 입력값(비밀번호 등)이 메시지에 섞이지 않게 필드 이름만 보여 준다
        fields = ", ".join(str(err["loc"][0]).upper() for err in e.errors())
        print(f"설정 오류: 환경변수 확인 필요 — {fields}", file=sys.stderr)
        raise SystemExit(2) from None
    # 3) 실행 — 예상 못 한 예외는 1
    try:
        code = asyncio.run(args.func(args, settings))
    except SystemExit:
        raise
    except Exception as e:
        print(f"실행 실패: {type(e).__name__}: {e}", file=sys.stderr)
        code = 1
    raise SystemExit(code)
