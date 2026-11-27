"""인덱서 단위테스트 (U-IDX) — LightRAG를 httpx.MockTransport로 흉내 낸다."""

import json
from datetime import datetime

import httpx

from nadri.core.tourapi import KST
from nadri.ingest.indexer import (
    IndexOutcome,
    LightRagClient,
    PageToIndex,
    from_file_source,
    index_pages,
    needs_indexing,
    outcome_to_values,
    to_file_source,
)

API_KEY = "lr-key"


class FakeLightRag:
    """경로별 응답을 스크립트로 정하는 가짜 LightRAG. 요청은 (메서드, 경로, 본문)으로 기록한다."""

    def __init__(self, *, track=None, exists=None, delete_status=200, insert_status=None):
        """
        Args:
            track: track_status 응답 상태 순서(예: ["processing", "processed"])
            exists: 삭제 확인 때 문서가 아직 있는지 순서(마지막 값 반복)
            delete_status: delete 응답 HTTP 코드
            insert_status: insert 응답 HTTP 코드 순서(기본 모두 200)
        """
        self.track = list(track or ["processed"])
        self.exists = list(exists or [False])
        self.delete_status = delete_status
        self.insert_status = list(insert_status or [])
        self.requests: list[tuple[str, str, dict | None]] = []
        self.headers: list[str | None] = []
        self.doc_id = "doc-new"

    def __call__(self, req: httpx.Request) -> httpx.Response:
        """요청 하나를 처리한다."""
        body = json.loads(req.content) if req.content else None
        self.requests.append((req.method, req.url.path, body))
        self.headers.append(req.headers.get("X-API-Key"))
        path = req.url.path
        if path == "/documents/text":
            code = self.insert_status.pop(0) if self.insert_status else 200
            if code == 409:
                return httpx.Response(409, json={"detail": "Document storage already contains 'x' (Status: failed)."})
            return httpx.Response(code, json={"status": "success", "message": "", "track_id": "insert_1"})
        if path.startswith("/documents/track_status/"):
            status = self.track.pop(0) if len(self.track) > 1 else self.track[0]
            doc = {"id": self.doc_id, "status": status, "file_path": "x", "error_msg": "llm error" if status == "failed" else None}
            return httpx.Response(200, json={"track_id": "insert_1", "documents": [doc], "total_count": 1})
        if path == "/documents/delete_document":
            if self.delete_status != 200:
                return httpx.Response(self.delete_status, json={"detail": "err"})
            return httpx.Response(200, json={"status": "deletion_started", "message": "", "doc_id": body["doc_ids"][0]})
        if path == "/documents/paginated":
            present = self.exists.pop(0) if len(self.exists) > 1 else self.exists[0]
            docs = [{"id": "doc-old", "file_path": "entity__12__1.md", "status": "processed"}] if present else []
            return httpx.Response(200, json={"documents": docs, "pagination": {"has_next": False}})
        return httpx.Response(404)

    def kinds(self) -> list[str]:
        """요청 순서를 짧은 이름으로."""
        names = {"/documents/text": "insert", "/documents/delete_document": "delete", "/documents/paginated": "exists"}
        return [names.get(p, "track" if p.startswith("/documents/track_status/") else p) for _, p, _ in self.requests]


class FakeTime:
    """가짜 시계·대기 — sleep이 시계를 앞으로 민다."""

    def __init__(self, step: float = 5.0):
        """step: sleep 한 번에 시계가 나아가는 초."""
        self.now = 0.0
        self.sleeps: list[float] = []
        self.step = step

    def clock(self) -> float:
        """현재 가짜 시각."""
        return self.now

    async def sleep(self, s: float) -> None:
        """대기 요청을 기록하고 시계를 민다."""
        self.sleeps.append(s)
        self.now += self.step


def page(path="entity/12/1.md", text="본문", h="h-new", old_hash=None, old_doc=None) -> PageToIndex:
    """테스트용 페이지."""
    return PageToIndex(path, text, h, old_hash, old_doc)


async def run(fake: FakeLightRag, pages, *, timeout_s=100.0, ft: FakeTime | None = None):
    """가짜 LightRAG로 index_pages를 실행한다."""
    ft = ft or FakeTime()
    client = LightRagClient("http://lightrag:9621", API_KEY, transport=httpx.MockTransport(fake))
    try:
        return await index_pages(client, pages, timeout_s=timeout_s, poll_interval_s=5.0, sleep=ft.sleep, clock=ft.clock), ft
    finally:
        await client.aclose()


def test_needs_indexing_table():
    """U-IDX-1: 판단 표."""
    assert needs_indexing("h", "h", "doc-1") is False
    assert needs_indexing("h2", "h", "doc-1") is True
    assert needs_indexing("h", None, None) is True
    assert needs_indexing("h", "h", None) is True


def test_file_source_roundtrip():
    """LightRAG가 basename만 남기므로 '/'를 '__'로 바꿔 보내고 되돌린다."""
    assert to_file_source("entity/12/126508.md") == "entity__12__126508.md"
    assert from_file_source("entity__12__126508.md") == "entity/12/126508.md"


async def test_same_hash_skipped_no_http():
    """U-IDX-2: 해시 같은 페이지 3개 → 모두 skipped, 요청 0건."""
    fake = FakeLightRag()
    pages = [page(f"entity/12/{i}.md", h="h", old_hash="h", old_doc=f"d{i}") for i in range(3)]
    out, _ = await run(fake, pages)
    assert [o.status for o in out] == ["skipped"] * 3 and fake.requests == []


async def test_new_page_indexed():
    """U-IDX-3: 새 페이지 → insert → track ×2, indexed·doc-new·새 해시, sleep(poll_interval_s)."""
    fake = FakeLightRag(track=["processing", "processed"])
    out, ft = await run(fake, [page()])
    assert fake.kinds() == ["insert", "track", "track"]
    assert out[0].status == "indexed" and out[0].doc_id == "doc-new" and out[0].content_hash == "h-new"
    assert ft.sleeps == [5.0]


async def test_changed_page_delete_first():
    """U-IDX-4: 바뀐 페이지 → delete(doc-old) → exists(False) → insert → track."""
    fake = FakeLightRag()
    out, _ = await run(fake, [page(old_hash="h-old", old_doc="doc-old")])
    assert fake.kinds() == ["delete", "exists", "insert", "track"]
    assert fake.requests[0][2]["doc_ids"] == ["doc-old"]
    assert out[0].status == "indexed"


async def test_delete_error_no_insert():
    """U-IDX-5: delete 500 → failed('삭제'), insert 없음."""
    fake = FakeLightRag(delete_status=500)
    out, _ = await run(fake, [page(old_hash="h-old", old_doc="doc-old")])
    assert out[0].status == "failed" and "삭제" in out[0].reason
    assert "insert" not in fake.kinds()


async def test_delete_never_finishes():
    """U-IDX-6: 삭제 후 계속 존재 → delete_timeout, insert 없음."""
    fake = FakeLightRag(exists=[True])
    out, _ = await run(fake, [page(old_hash="h-old", old_doc="doc-old")], timeout_s=20)
    assert out[0].status == "failed" and out[0].reason == "delete_timeout"
    assert "insert" not in fake.kinds()


async def test_track_failed():
    """U-IDX-7: 처리 실패 → failed, 사유 포함."""
    fake = FakeLightRag(track=["failed"])
    out, _ = await run(fake, [page()])
    assert out[0].status == "failed" and "llm error" in out[0].reason and out[0].content_hash is None


async def test_track_timeout_marks_remaining():
    """U-IDX-8: 끝나지 않음 + 시계가 timeout_s를 넘김 → 남은 페이지 모두 timeout."""
    fake = FakeLightRag(track=["processing"])
    out, _ = await run(fake, [page("entity/12/1.md"), page("entity/12/2.md")], timeout_s=12)
    assert [(o.status, o.reason) for o in out] == [("failed", "timeout")] * 2


async def test_api_key_header_on_all_requests():
    """U-IDX-9: 모든 요청에 X-API-Key 헤더(v1.5.7 utils_api.py에서 확인한 이름)."""
    fake = FakeLightRag()
    await run(fake, [page(old_hash="h-old", old_doc="doc-old")])
    assert fake.headers and all(h == API_KEY for h in fake.headers)


async def test_insert_body():
    """U-IDX-10: insert 본문 file_source = to_file_source(path), text = 페이지 내용."""
    fake = FakeLightRag()
    p = page("entity/12/126508.md", text="# 경복궁")
    await run(fake, [p])
    body = fake.requests[0][2]
    assert body == {"text": "# 경복궁", "file_source": "entity__12__126508.md"}


async def test_insert_conflict_cleans_stale_and_retries():
    """같은 file_source 잔여 문서(이전 실패)로 409 → 그 문서를 지우고 한 번 다시 넣는다."""
    fake = FakeLightRag(insert_status=[409, 200], exists=[True, True, False])
    out, _ = await run(fake, [page("entity/12/1.md")])
    assert fake.kinds() == ["insert", "exists", "delete", "exists", "exists", "insert", "track"]
    assert out[0].status == "indexed"


def test_outcome_to_values():
    """U-IDX-11: indexed → 세 값 채움 / failed → 셋 다 None / skipped → None."""
    now = datetime(2026, 11, 21, 10, 0, tzinfo=KST)
    ok = IndexOutcome("p", "indexed", "doc-1", "h", None, 1.0)
    bad = IndexOutcome("p", "failed", None, None, "x", 1.0)
    skip = IndexOutcome("p", "skipped", None, None, None, 0.0)
    assert outcome_to_values(ok, now) == {"content_hash": "h", "lightrag_doc_id": "doc-1", "indexed_at": now}
    assert outcome_to_values(bad, now) == {"content_hash": None, "lightrag_doc_id": None, "indexed_at": None}
    assert outcome_to_values(skip, now) is None
