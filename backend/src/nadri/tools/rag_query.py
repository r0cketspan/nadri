"""rag_query 툴 — LightRAG 후보 30개 → 리랭커(ONNX) 재채점 → 상위 5개 + 출처·기준일."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import select

from nadri.core.models.tour import WikiPage
from nadri.ingest.indexer import LightRagError, from_file_source
from nadri.ingest.wiki.render import SOURCE_LABEL
from nadri.tools.reranker import rerank

if TYPE_CHECKING:
    from nadri.tools.server import ToolDeps

log = logging.getLogger(__name__)

MAX_QUESTION = 500
QUERY_TIMEOUT_S = 30.0
UNAVAILABLE = "지식 검색을 할 수 없습니다"


@dataclass(frozen=True)
class Candidate:
    """LightRAG 후보 문단 하나."""

    chunk_id: str | None
    file_path: str | None
    content: str


@dataclass(frozen=True)
class PageMeta:
    """후보 문단이 속한 위키 페이지의 메타(wiki_pages)."""

    contentid: str | None
    title: str
    as_of: str | None  # YYYY-MM-DD


def parse_query_data(payload: dict) -> list[Candidate]:
    """
    /query/data 응답에서 청크 목록을 뽑는다(순수 함수).

    Args:
        payload: 응답 JSON — {"status", "data": {"entities", "relationships", "chunks", "references"}, "metadata"}

    Returns:
        LightRAG 순위 그대로의 Candidate 목록(내용 없는 청크는 버림)

    Raises:
        LightRagError: data.chunks가 없는 등 형식이 다를 때
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("chunks"), list):
        raise LightRagError("LightRAG /query/data 응답 형식이 다릅니다")
    return [
        Candidate(c.get("chunk_id"), c.get("file_path"), str(c["content"]))
        for c in data["chunks"]
        if isinstance(c, dict) and c.get("content")
    ]


async def fetch_candidates(http: httpx.AsyncClient, question: str, *, top_k: int) -> tuple[list[Candidate], dict]:
    """
    POST /query/data {query, mode:'mix', top_k, chunk_top_k} → (후보, 원본 응답).

    Args:
        http: LightRAG용 클라이언트(base_url·X-API-Key 설정됨)
        question: 질문
        top_k: 후보 수(엔티티·관계 top_k와 청크 chunk_top_k에 같은 값)

    Raises:
        httpx.HTTPError, LightRagError: 호출·형식 오류
    """
    resp = await http.post(
        "/query/data",
        json={"query": question, "mode": "mix", "top_k": top_k, "chunk_top_k": top_k},
        timeout=QUERY_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    return parse_query_data(payload), payload


def _default_lookup(deps: ToolDeps) -> Callable[[list[str]], Awaitable[dict[str, PageMeta]]]:
    """deps.sf로 wiki_pages를 path IN (...) 조회하는 기본 lookup을 만든다."""

    async def lookup(paths: list[str]) -> dict[str, PageMeta]:
        """경로 목록의 wiki_pages 메타를 돌려준다(없는 경로는 빠짐)."""
        async with deps.sf() as s:
            rows = (
                await s.execute(
                    select(WikiPage.path, WikiPage.contentid, WikiPage.title, WikiPage.as_of).where(
                        WikiPage.path.in_(paths)
                    )
                )
            ).all()
        return {
            r.path: PageMeta(r.contentid, r.title, r.as_of.isoformat() if r.as_of else None) for r in rows
        }

    return lookup


async def rag_query(
    question: str,
    deps: ToolDeps,
    lookup_pages: Callable[[list[str]], Awaitable[dict[str, PageMeta]]] | None = None,
) -> dict:
    """
    질문으로 위키 문단 후보 30개를 받아 리랭크하고 상위 5개를 출처·기준일과 함께 돌려준다.

    Args:
        question: 사용자 질문(1~500자)
        deps: 공유 자원(설정·LightRAG 클라이언트·리랭커·세션)
        lookup_pages: path 목록 → PageMeta (테스트 주입용, 기본은 wiki_pages 조회)

    Returns:
        {"items": [{contentid, title, source, as_of, path, score, text}], "count": n} — 점수 내림차순

    Raises:
        ValueError: 질문이 비었거나 너무 김(HTTP 호출 없음)
        RuntimeError: LightRAG·DB 오류(메시지 "지식 검색을 할 수 없습니다")
    """
    t0 = time.monotonic()
    # 1) 입력 검사
    q = question.strip()
    if not q or len(q) > MAX_QUESTION:
        raise ValueError(f"질문은 1~{MAX_QUESTION}자여야 합니다")

    # 2) LightRAG 후보 조회 — 실패 사유는 로그에만, 결과 메시지는 짧게
    try:
        candidates, _ = await fetch_candidates(deps.lightrag_http, q, top_k=deps.settings.rag_candidates)
    except (httpx.HTTPError, LightRagError, ValueError) as e:
        log.warning("tool=rag_query lightrag_error=%s", type(e).__name__)
        raise RuntimeError(UNAVAILABLE) from None
    lightrag_ms = (time.monotonic() - t0) * 1000

    # 3) 후보가 없으면 리랭커를 부르지 않는다
    if not candidates:
        log.info("tool=rag_query candidates=0 lightrag_ms=%d rerank_ms=0 total_ms=%d", lightrag_ms, lightrag_ms)
        return {"items": [], "count": 0}

    # 4) 리랭크 → 상위 k
    t1 = time.monotonic()
    top = await rerank(deps.reranker, q, [c.content for c in candidates], deps.settings.rag_top_k)
    rerank_ms = (time.monotonic() - t1) * 1000

    # 5) 페이지 메타 조회 — 메타 없는 후보는 버리고 다시 채우지 않는다
    paths = {i: from_file_source(candidates[i].file_path) for i, _ in top if candidates[i].file_path}
    try:
        metas = await (lookup_pages or _default_lookup(deps))(sorted(set(paths.values())))
    except Exception as e:  # DB 오류도 짧은 메시지로
        log.warning("tool=rag_query db_error=%s", type(e).__name__)
        raise RuntimeError(UNAVAILABLE) from None

    # 6) 결과 항목(점수 내림차순 유지)
    items = []
    for i, score in top:
        meta = metas.get(paths.get(i, ""))
        if meta is None:
            continue
        items.append({
            "contentid": meta.contentid,
            "title": meta.title,
            "source": SOURCE_LABEL,
            "as_of": meta.as_of,
            "path": paths[i],
            "score": round(float(score), 4),
            "text": candidates[i].content,
        })

    # 7) 측정용 로그(질문 원문 없음)
    log.info(
        "tool=rag_query candidates=%d lightrag_ms=%d rerank_ms=%d total_ms=%d",
        len(candidates), lightrag_ms, rerank_ms, (time.monotonic() - t0) * 1000,
    )
    return {"items": items, "count": len(items)}
