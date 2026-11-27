"""LightRAG 문서 API 클라이언트와 '바뀐 페이지만 delete→insert' 인덱싱.

LightRAG v1.5.7 문서 API(lightrag/api/routers/document_routes.py에서 확인):
- POST   /documents/text                {text, file_source} → {status, message, track_id}
         같은 file_source가 이미 있으면 409("already contains"), 삭제 진행 중이면 409
- GET    /documents/track_status/{id}   → {documents: [{id, status, file_path, error_msg, …}]}
- DELETE /documents/delete_document     {doc_ids, delete_file, delete_llm_cache} → status deletion_started|busy|not_allowed
         (삭제는 백그라운드로 진행 — 사라질 때까지 목록으로 확인)
- POST   /documents/paginated           {page, page_size(≤200), sort_field, sort_direction} → {documents, pagination}
- GET    /documents/status_counts       → {status_counts: {상태: 수}}
인증 헤더는 X-API-Key. 문서 상태 문자열은 소문자(processed, failed, …).
LightRAG는 file_source를 basename으로 바꿔 저장하므로, 경로의 '/'를 '__'로 바꿔 보낸다(to_file_source).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from nadri.core.models.tour import WikiPage
from nadri.core.tourapi import KST

PAGE_SIZE = 200  # /documents/paginated 최대값


def to_file_source(path: str) -> str:
    """
    위키 상대 경로를 LightRAG file_source로 바꾼다(LightRAG가 basename만 남기므로 '/'를 '__'로).

    Args:
        path: 예) 'entity/12/126508.md'

    Returns:
        예) 'entity__12__126508.md'
    """
    return path.replace("/", "__")


def from_file_source(file_source: str) -> str:
    """
    LightRAG가 돌려준 file_path를 위키 상대 경로로 되돌린다(to_file_source의 역).

    Args:
        file_source: 예) 'entity__12__126508.md'

    Returns:
        예) 'entity/12/126508.md'
    """
    return file_source.replace("__", "/")


@dataclass(frozen=True)
class PageToIndex:
    """인덱싱 후보 페이지. old_*는 wiki_pages에 저장된 이전 값."""

    path: str
    text: str
    content_hash: str
    old_hash: str | None
    old_doc_id: str | None


@dataclass(frozen=True)
class IndexOutcome:
    """페이지 하나의 처리 결과."""

    path: str
    status: Literal["skipped", "indexed", "failed"]
    doc_id: str | None
    content_hash: str | None
    reason: str | None
    elapsed_s: float


class LightRagError(Exception):
    """LightRAG 호출 실패(메시지에 키·내부 URL 없음)."""


class LightRagConflict(LightRagError):
    """409 — 같은 file_source가 이미 있거나 삭제가 진행 중이라 넣을 수 없음."""

    def __init__(self, detail: str) -> None:
        """
        Args:
            detail: LightRAG가 돌려준 사유 문자열
        """
        super().__init__(f"LightRAG 409: {detail}")
        self.detail = detail


class LightRagBusy(LightRagError):
    """삭제 요청이 파이프라인 사용 중(busy)이라 거절됨 — 잠시 뒤 다시 시도."""


class LightRagClient:
    """LightRAG 서버 문서 API 클라이언트(헤더 X-API-Key)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """
        Args:
            base_url: 예) http://lightrag:9621
            api_key: LIGHTRAG_API_KEY
            timeout: 요청 타임아웃(초)
            transport: 테스트용 httpx 전송 계층
        """
        self._http = httpx.AsyncClient(
            base_url=base_url, headers={"X-API-Key": api_key}, timeout=timeout, transport=transport
        )

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """
        요청을 보내고 JSON을 돌려준다.

        Raises:
            LightRagConflict: 409
            LightRagError: 그 밖의 HTTP 오류·연결 실패
        """
        # 1) 요청 — 연결 오류는 내부 주소 없이 감싼다
        try:
            resp = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            raise LightRagError(f"LightRAG {method} {path} 연결 실패({type(e).__name__})") from None
        # 2) 409는 사유를 살려 따로 던진다(재시도 판단용)
        if resp.status_code == 409:
            try:
                detail = str(resp.json().get("detail", ""))
            except ValueError:
                detail = resp.text[:200]
            raise LightRagConflict(detail)
        if resp.status_code >= 400:
            raise LightRagError(f"LightRAG {method} {path} HTTP {resp.status_code}")
        return resp.json()

    async def insert_text(self, text: str, file_source: str) -> str:
        """
        문서 하나를 넣는다(처리는 LightRAG 백그라운드).

        Args:
            text: 페이지 전체 내용
            file_source: to_file_source(경로)

        Returns:
            처리 상태 조회용 track_id
        """
        data = await self._request("POST", "/documents/text", json={"text": text, "file_source": file_source})
        return data["track_id"]

    async def track_status(self, track_id: str) -> list[dict]:
        """
        track_id에 묶인 문서 상태 목록을 돌려준다.

        Returns:
            [{id, status, file_path, error_msg, …}] — status는 소문자 문자열
        """
        data = await self._request("GET", f"/documents/track_status/{track_id}")
        return data.get("documents") or []

    async def delete_documents(self, doc_ids: list[str]) -> None:
        """
        문서 삭제를 시작한다(백그라운드 진행 — 완료는 document_exists로 확인).

        Raises:
            LightRagBusy: 파이프라인 사용 중이라 거절
            LightRagError: 거부·HTTP 오류
        """
        data = await self._request(
            "DELETE",
            "/documents/delete_document",
            json={"doc_ids": doc_ids, "delete_file": False, "delete_llm_cache": False},
        )
        status = data.get("status")
        if status == "busy":
            raise LightRagBusy("LightRAG 사용 중")
        if status != "deletion_started":
            raise LightRagError(f"LightRAG 삭제 거부: {status}")

    async def list_documents(self) -> list[dict]:
        """
        전체 문서 목록을 페이지를 넘기며 모은다(수천 건 규모 가정).

        Returns:
            [{id, status, file_path, …}]
        """
        docs: list[dict] = []
        page = 1
        while True:
            data = await self._request(
                "POST",
                "/documents/paginated",
                json={"page": page, "page_size": PAGE_SIZE, "sort_field": "id", "sort_direction": "asc"},
            )
            docs += data.get("documents") or []
            if not (data.get("pagination") or {}).get("has_next"):
                return docs
            page += 1

    async def document_exists(self, doc_id: str) -> bool:
        """문서 ID가 LightRAG 문서 목록에 있으면 True(문서 단건 조회 API가 없어 목록으로 확인)."""
        return any(d.get("id") == doc_id for d in await self.list_documents())

    async def find_doc_ids(self, file_source: str) -> list[str]:
        """같은 file_source로 남아 있는 문서 ID들(이전 실패·타임아웃 잔여물 정리용)."""
        return [d["id"] for d in await self.list_documents() if d.get("file_path") == file_source]

    async def count_documents(self) -> dict[str, int]:
        """상태별 문서 수를 돌려준다."""
        data = await self._request("GET", "/documents/status_counts")
        return data.get("status_counts") or {}

    async def aclose(self) -> None:
        """HTTP 연결을 닫는다."""
        await self._http.aclose()


def needs_indexing(new_hash: str, old_hash: str | None, old_doc_id: str | None) -> bool:
    """
    인덱싱이 필요한지 판단한다.

    Args:
        new_hash: 이번에 렌더한 내용 해시
        old_hash: wiki_pages.content_hash(인덱싱 성공 때만 채워짐)
        old_doc_id: wiki_pages.lightrag_doc_id

    Returns:
        새 해시가 저장 해시와 다르거나, 이전 인덱싱 기록(doc_id)이 없으면 True
    """
    return new_hash != old_hash or old_doc_id is None


async def index_pages(
    client: LightRagClient,
    pages: list[PageToIndex],
    *,
    timeout_s: float,
    poll_interval_s: float = 5.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> list[IndexOutcome]:
    """
    바뀐 페이지만 LightRAG에서 delete→insert하고 처리 완료까지 기다려 결과를 돌려준다(DB는 건드리지 않음).

    Args:
        client: LightRAG 클라이언트
        pages: 후보 페이지
        timeout_s: 삭제 확인·넣기·처리 완료 대기를 합친 전체 상한(초)
        poll_interval_s: 상태 확인 간격(초)
        sleep, clock: 테스트 주입용 대기·시계

    Returns:
        입력 순서대로의 IndexOutcome 목록
    """
    start = clock()
    deadline = start + timeout_s
    results: dict[str, IndexOutcome] = {}

    def done(p: PageToIndex, status, doc_id=None, reason=None) -> None:
        """결과 하나를 기록한다(indexed일 때만 새 해시를 남김)."""
        results[p.path] = IndexOutcome(
            p.path, status, doc_id, p.content_hash if status == "indexed" else None, reason, clock() - start
        )

    async def remove(doc_id: str) -> str | None:
        """문서 삭제를 요청하고 사라질 때까지 기다린다. 실패 사유(없으면 None)를 돌려준다."""
        # 1) 삭제 요청 — 사용 중이면 간격을 두고 다시
        while True:
            try:
                await client.delete_documents([doc_id])
                break
            except LightRagBusy:
                if clock() > deadline:
                    return "delete_timeout"
                await sleep(poll_interval_s)
            except LightRagError as e:
                return f"이전 문서 삭제 실패: {e}"
        # 2) 백그라운드 삭제가 끝나 목록에서 사라질 때까지 확인
        while True:
            try:
                if not await client.document_exists(doc_id):
                    return None
            except LightRagError as e:
                return f"이전 문서 삭제 확인 실패: {e}"
            if clock() > deadline:
                return "delete_timeout"
            await sleep(poll_interval_s)

    async def insert(p: PageToIndex) -> str:
        """페이지를 넣고 track_id를 돌려준다. 같은 file_source 잔여 문서가 있으면 한 번 지우고 다시 넣는다."""
        source = to_file_source(p.path)
        cleaned = False
        while True:
            try:
                return await client.insert_text(p.text, source)
            except LightRagConflict as e:
                # 1) 이전 실패·타임아웃으로 남은 같은 이름 문서 → 지우고 다시
                if "already contains" in e.detail and not cleaned:
                    for stale in await client.find_doc_ids(source):
                        reason = await remove(stale)
                        if reason:
                            raise LightRagError(reason) from None
                    cleaned = True
                    continue
                # 2) 삭제 진행 중 등 일시적 거절 → 기다렸다 다시
                if clock() > deadline:
                    raise LightRagError("insert_timeout") from None
                await sleep(poll_interval_s)

    # 1) 해시가 같고 doc_id가 있으면 건너뛴다(HTTP 호출 없음)
    targets = []
    for p in pages:
        if needs_indexing(p.content_hash, p.old_hash, p.old_doc_id):
            targets.append(p)
        else:
            done(p, "skipped")

    # 2) 이전 문서를 먼저 지운다 — 실패하면 그 페이지는 넣지 않는다(중복 방지 우선)
    ready = []
    for p in targets:
        reason = await remove(p.old_doc_id) if p.old_doc_id else None
        if reason:
            done(p, "failed", reason=reason)
        else:
            ready.append(p)

    # 3) 넣기 — track_id를 모은다
    pending: dict[str, tuple[str, PageToIndex]] = {}  # path → (track_id, 페이지)
    for p in ready:
        try:
            pending[p.path] = (await insert(p), p)
        except LightRagError as e:
            done(p, "failed", reason=str(e))

    # 4) 처리 완료(processed)·실패(failed)·시간 초과까지 상태를 확인한다
    while pending:
        for path, (track_id, p) in list(pending.items()):
            try:
                docs = await client.track_status(track_id)
            except LightRagError as e:
                done(p, "failed", reason=str(e))
                del pending[path]
                continue
            doc = docs[0] if docs else None
            status = str(doc.get("status", "")).lower() if doc else ""
            if status == "processed":
                done(p, "indexed", doc_id=doc["id"])
                del pending[path]
            elif status == "failed":
                done(p, "failed", doc_id=None, reason=f"LightRAG 처리 실패: {doc.get('error_msg') or ''}".strip())
                del pending[path]
        if not pending:
            break
        if clock() > deadline:
            for _, p in pending.values():
                done(p, "failed", reason="timeout")
            break
        await sleep(poll_interval_s)

    return [results[p.path] for p in pages]


def outcome_to_values(o: IndexOutcome, now: datetime) -> dict | None:
    """
    apply_outcomes가 쓰는 순수 함수: 결과 하나를 wiki_pages 갱신 값으로 바꾼다.

    Args:
        o: 처리 결과
        now: indexed_at에 넣을 시각

    Returns:
        indexed → 해시·doc_id·시각, failed → 셋 다 None(다음 실행에서 재시도), skipped → None(변경 없음)
    """
    if o.status == "indexed":
        return {"content_hash": o.content_hash, "lightrag_doc_id": o.doc_id, "indexed_at": now}
    if o.status == "failed":
        return {"content_hash": None, "lightrag_doc_id": None, "indexed_at": None}
    return None


async def apply_outcomes(session: AsyncSession, outcomes: list[IndexOutcome]) -> None:
    """
    인덱싱 결과를 wiki_pages에 반영한다(커밋은 호출부).

    Args:
        session: 열린 세션
        outcomes: index_pages 결과
    """
    now = datetime.now(KST)
    for o in outcomes:
        values = outcome_to_values(o, now)
        if values is not None:
            await session.execute(update(WikiPage).where(WikiPage.path == o.path).values(**values))
