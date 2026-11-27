"""rag_query 단위테스트 (U-RAG) — LightRAG MockTransport + 가짜 리랭커 + 가짜 lookup."""

import json
import logging

import httpx
import pytest

from nadri.ingest.indexer import LightRagError
from nadri.tools import reranker as reranker_mod
from nadri.tools.rag_query import PageMeta, parse_query_data, rag_query
from nadri.tools.reranker import top_k_indices
from nadri.tools.server import ToolDeps
from tests.conftest import load_fixture, make_settings

LR_KEY = "lr-secret-key"


class FakeReranker:
    """입력 순서대로 정해진 점수를 돌려주는 가짜 CrossEncoder."""

    def __init__(self, scores):
        """scores: 후보 순서대로 돌려줄 점수."""
        self.scores = scores
        self.calls = 0

    def score(self, query, passages):
        """호출 횟수를 세고 정해진 점수를 돌려준다."""
        self.calls += 1
        return self.scores[: len(passages)]


def chunks(n: int) -> dict:
    """청크 n개짜리 /query/data 응답."""
    return {"status": "success", "message": "", "metadata": {}, "data": {
        "entities": [], "relationships": [], "references": [],
        "chunks": [{"content": f"문단 {i}", "file_path": f"entity__12__{i}.md", "chunk_id": f"c{i}"} for i in range(n)],
    }}


def make_deps(handler, scores=(0.1, 0.9, 0.5, 0.7, 0.3, 0.8, 0.2)):
    """가짜 LightRAG·리랭커로 ToolDeps를 만든다(DB는 lookup 주입으로 대체)."""
    http = httpx.AsyncClient(
        base_url="http://lightrag:9621", headers={"X-API-Key": LR_KEY}, transport=httpx.MockTransport(handler)
    )
    return ToolDeps(settings=make_settings(), sf=None, lightrag_http=http, reranker=FakeReranker(list(scores)))


def ok_handler(n: int, seen: list | None = None):
    """청크 n개를 돌려주고 요청을 기록하는 핸들러."""

    def handler(req: httpx.Request) -> httpx.Response:
        """요청을 기록하거나 검사하고 가짜 응답을 돌려준다."""
        if seen is not None:
            seen.append(req)
        return httpx.Response(200, json=chunks(n))

    return handler


async def lookup_all(paths):
    """모든 경로에 메타가 있는 가짜 lookup."""
    return {p: PageMeta(p.split("/")[-1][:-3], f"장소 {p}", "2026-11-21") for p in paths}


def test_parse_query_data_fixture():
    """U-RAG-1: 픽스처 청크 3개 → Candidate 3개, 순서 유지."""
    cands = parse_query_data(json.loads(load_fixture("lightrag/query_data.json")))
    assert [c.chunk_id for c in cands] == ["chunk-0", "chunk-1", "chunk-2"]
    assert cands[0].file_path == "entity__12__126500.md"


def test_parse_query_data_missing_chunks():
    """U-RAG-2: chunks 키 없음 → LightRagError."""
    with pytest.raises(LightRagError):
        parse_query_data({"data": {"entities": []}})


def test_top_k_ties():
    """U-RAG-3: 동점은 원래 순서."""
    assert top_k_indices([0.1, 0.9, 0.5, 0.9], 2) == [1, 3]


def test_top_k_short():
    """U-RAG-4: 후보가 k보다 적음."""
    assert top_k_indices([0.3], 5) == [0]


async def test_rag_query_ok():
    """U-RAG-5: 후보 7 → 상위 5, 점수 내림차순, 필수 필드."""
    deps = make_deps(ok_handler(7))
    out = await rag_query("경복궁 관람 시간", deps, lookup_pages=lookup_all)
    scores = [i["score"] for i in out["items"]]
    assert out["count"] == 5 and scores == sorted(scores, reverse=True)
    assert [i["path"] for i in out["items"]][:2] == ["entity/12/1.md", "entity/12/5.md"]
    for item in out["items"]:
        assert all(item[k] for k in ("contentid", "source", "as_of", "path", "text")) and item["score"]


async def test_request_body_and_header():
    """U-RAG-6: mode mix, 후보 수 30, X-API-Key."""
    seen = []
    await rag_query("질문", make_deps(ok_handler(3, seen)), lookup_pages=lookup_all)
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/query/data"
    assert body["mode"] == "mix" and body["top_k"] == 30 and body["chunk_top_k"] == 30
    assert seen[0].headers["X-API-Key"] == LR_KEY


async def test_no_candidates():
    """U-RAG-7: 후보 0 → 빈 결과, 리랭커 호출 없음."""
    deps = make_deps(ok_handler(0))
    assert await rag_query("질문", deps, lookup_pages=lookup_all) == {"items": [], "count": 0}
    assert deps.reranker.calls == 0


async def test_missing_meta_not_refilled():
    """U-RAG-8: 상위 5개 중 1개 메타 없음 → 4개(다시 채우지 않음)."""

    async def lookup(paths):
        """1번 페이지 메타만 빠진 lookup."""
        metas = await lookup_all(paths)
        metas.pop("entity/12/1.md")
        return metas

    out = await rag_query("질문", make_deps(ok_handler(7)), lookup_pages=lookup)
    assert out["count"] == 4


@pytest.mark.parametrize("failure", ["500", "timeout"])
async def test_lightrag_failure_message(failure):
    """U-RAG-9: LightRAG 500·타임아웃 → 짧은 한국어 메시지, 내부 URL·키 없음."""

    def handler(req):
        """요청을 기록하거나 검사하고 가짜 응답을 돌려준다."""
        if failure == "timeout":
            raise httpx.ReadTimeout("느림", request=req)
        return httpx.Response(500, text="internal")

    with pytest.raises(RuntimeError) as e:
        await rag_query("질문", make_deps(handler), lookup_pages=lookup_all)
    msg = str(e.value)
    assert "지식 검색을 할 수 없습니다" in msg and "lightrag:9621" not in msg and LR_KEY not in msg


@pytest.mark.parametrize("q", ["", "   ", "가" * 501])
async def test_bad_question(q):
    """U-RAG-10: 빈 질문·공백·501자 → ValueError, HTTP 호출 없음."""
    seen = []
    with pytest.raises(ValueError):
        await rag_query(q, make_deps(ok_handler(3, seen)), lookup_pages=lookup_all)
    assert seen == []


async def test_rerank_runs_in_thread(monkeypatch):
    """U-RAG-11: 리랭커 score는 asyncio.to_thread 경유로 호출된다."""
    used = []
    real = reranker_mod.asyncio.to_thread

    async def spy(fn, *args, **kwargs):
        """to_thread로 넘어온 함수를 기록하고 원래 to_thread로 실행."""
        used.append(fn)
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(reranker_mod.asyncio, "to_thread", spy)
    deps = make_deps(ok_handler(3))
    await rag_query("질문", deps, lookup_pages=lookup_all)
    assert used and used[0] == deps.reranker.score


async def test_log_line(caplog):
    """U-RAG-12: 측정 로그 — tool·candidates·rerank_ms, 질문 원문 없음."""
    caplog.set_level(logging.INFO, logger="nadri.tools.rag_query")
    await rag_query("비밀스러운 질문", make_deps(ok_handler(7)), lookup_pages=lookup_all)
    text = caplog.text
    assert "tool=rag_query" in text and "candidates=7" in text and "rerank_ms=" in text
    assert "비밀스러운 질문" not in text
