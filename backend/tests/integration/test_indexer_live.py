"""통합: 실 LightRAG 인덱서 왕복 (I-8, A16). 테스트 페이지 1~2개분 인덱싱 비용이 든다."""

import uuid

import pytest

from nadri.ingest.indexer import LightRagClient, PageToIndex, index_pages
from nadri.ingest.wiki.render import content_hash

pytestmark = pytest.mark.integration


async def test_index_roundtrip(app_settings):
    """I-8: indexed(A) → 같은 내용 skipped(요청 0) → 내용 변경 indexed(B≠A), A 삭제됨, 문서 수 불변."""
    path = f"entity/test/{uuid.uuid4()}.md"
    client = LightRagClient(app_settings.lightrag_url, app_settings.lightrag_api_key.get_secret_value())
    doc_b = None
    try:
        # 1) 첫 인덱싱
        text_a = f"# 통합 테스트 페이지\n\n관광지 ID: {path}\n\n테스트용 문단 A."
        [a] = await index_pages(client, [PageToIndex(path, text_a, content_hash(text_a), None, None)], timeout_s=600)
        assert a.status == "indexed" and a.doc_id
        count_after_a = sum((await client.count_documents()).values())

        # 2) 같은 내용 → skipped, 요청 없음
        sent = []

        async def record(req):
            """보낸 요청을 기록한다."""
            sent.append(req)

        client._http.event_hooks["request"].append(record)
        [s] = await index_pages(client, [PageToIndex(path, text_a, a.content_hash, a.content_hash, a.doc_id)], timeout_s=60)
        client._http.event_hooks["request"].clear()
        assert s.status == "skipped" and sent == []

        # 3) 내용 변경 → delete A → insert B
        text_b = text_a.replace("문단 A", "문단 B")
        [b] = await index_pages(
            client, [PageToIndex(path, text_b, content_hash(text_b), a.content_hash, a.doc_id)], timeout_s=600
        )
        doc_b = b.doc_id
        assert b.status == "indexed" and b.doc_id != a.doc_id
        assert await client.document_exists(a.doc_id) is False
        assert sum((await client.count_documents()).values()) == count_after_a
    finally:
        if doc_b:
            await client.delete_documents([doc_b])
        await client.aclose()
