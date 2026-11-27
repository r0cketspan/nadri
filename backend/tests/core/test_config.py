"""설정·ORM COMMENT 단위테스트 (U-CFG)."""

import pytest

from nadri.core.config import Settings, require
from nadri.core.models import Base
from tests.conftest import make_settings

# spec §3.2 표 = ERD(docs/images/src/erd.py) 한글 명칭
EXPECTED_COMMENTS = {
    "tour_items": ("관광 정보", {
        "contentid": "관광지 ID", "content_type_id": "관광 유형", "area": "지역", "sigungu_code": "시군구 코드",
        "title": "명칭", "addr": "주소", "lat": "위도", "lng": "경도", "tel": "전화번호", "usetime": "이용시간",
        "fee": "이용요금", "restdate": "휴무일", "event_start": "행사 시작일", "event_end": "행사 종료일",
        "extra": "유형별 상세", "modifiedtime": "원천 수정 일시", "detail_synced_at": "상세 수집 일시",
        "as_of": "기준일", "deleted_at": "삭제 일시", "updated_at": "수정 일시",
    }),
    "wiki_pages": ("위키 페이지", {
        "path": "페이지 경로", "kind": "페이지 종류", "contentid": "관광지 ID", "title": "제목", "area": "지역",
        "sigungu_code": "시군구 코드", "as_of": "기준일", "content_hash": "내용 해시",
        "lightrag_doc_id": "RAG 문서 ID", "indexed_at": "인덱싱 일시",
    }),
    "ingest_runs": ("수집 실행 이력", {
        "id": "실행 ID", "kind": "실행 종류", "started_at": "시작 일시", "finished_at": "종료 일시",
        "status": "결과", "stats": "처리 통계", "lint": "점검 결과", "error": "오류 메시지",
    }),
    "ingest_state": ("수집 상태", {"key": "상태 키", "value": "상태 값"}),
}


def test_database_url_encodes_password():
    """U-CFG-1: 비밀번호의 @ : / 를 URL 인코딩한다."""
    s = make_settings(db_user="nadri_app", db_password="p@ss:w/rd")
    assert s.database_url == "postgresql+asyncpg://nadri_app:p%40ss%3Aw%2Frd@postgres:5432/nadri"


def test_repr_hides_secret():
    """U-CFG-2: repr에 비밀값이 나오지 않는다."""
    s = make_settings(tools_api_key="secret-xyz")
    assert "secret-xyz" not in repr(s)
    assert "secret-xyz" not in str(s)


def test_env_is_read(monkeypatch):
    """환경변수에서 값을 읽는다(compose 주입 방식)."""
    monkeypatch.setenv("DB_USER", "nadri_tools")
    monkeypatch.setenv("DB_PASSWORD", "x")
    monkeypatch.setenv("RAG_CANDIDATES", "20")
    s = Settings()
    assert s.db_user == "nadri_tools" and s.rag_candidates == 20


def test_orm_comments_match_erd():
    """U-CFG-3: 4테이블의 테이블·컬럼 COMMENT가 spec §3.2(=ERD)와 정확히 같다."""
    assert set(Base.metadata.tables) == set(EXPECTED_COMMENTS)
    for name, (table_comment, cols) in EXPECTED_COMMENTS.items():
        table = Base.metadata.tables[name]
        assert table.comment == table_comment
        assert {c.name: c.comment for c in table.columns} == cols


def test_migration_comments_match_orm():
    """U-CFG-3 보강: 테이블 생성 스크립트 0001의 COMMENT도 ORM과 같다(소스에 같은 문자열이 있음)."""
    from pathlib import Path

    src = (Path(__file__).parents[2] / "alembic/versions/0001_tour_ingest.py").read_text(encoding="utf-8")
    for table_comment, cols in EXPECTED_COMMENTS.values():
        assert f'comment="{table_comment}"' in src
        for col, comment in cols.items():
            assert f'"{col}"' in src and f'comment="{comment}"' in src


def test_require_missing_exits_2(capsys):
    """U-CFG-4: 값이 없으면 SystemExit(2), 메시지에 키 이름."""
    with pytest.raises(SystemExit) as e:
        require(None, "TOURAPI_SERVICE_KEY")
    assert e.value.code == 2
    assert "TOURAPI_SERVICE_KEY" in capsys.readouterr().err
