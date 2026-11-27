"""엔티티 렌더 단위테스트 (U-REN)."""

from dataclasses import asdict
from datetime import datetime, timedelta

import yaml

from nadri.core.models.tour import TourItem
from nadri.core.tourapi import KST
from nadri.ingest.upsert import build_record
from nadri.ingest.wiki.render import content_hash, entity_path, render_entity, write_page
from tests.conftest import FIXTURES, load_item

UPDATED = datetime(2026, 11, 21, 10, 0, tzinfo=KST)


def make_item(**overrides) -> TourItem:
    """경복궁 픽스처로 만든 TourItem(DB 없이)."""
    rec = build_record(
        "서울",
        load_item("tourapi/common_126508.json"),
        load_item("tourapi/intro_126508.json"),
        load_item("tourapi/info_126508.json"),
        UPDATED,
    )
    values = {**asdict(rec), "updated_at": UPDATED, "deleted_at": None}
    values.update(overrides)
    return TourItem(**values)


def frontmatter(text: str) -> dict:
    """--- 사이 YAML을 파싱한다."""
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_snapshot():
    """U-REN-1: 스냅샷과 바이트 단위로 같다."""
    expected = (FIXTURES / "wiki/entity_126508.md").read_text(encoding="utf-8")
    assert render_entity(make_item()) == expected


def test_deterministic_hash():
    """U-REN-2: 두 번 렌더 → 같은 문자열·해시(64자 16진)."""
    a, b = render_entity(make_item()), render_entity(make_item())
    assert a == b and content_hash(a) == content_hash(b)
    assert len(content_hash(a)) == 64 and int(content_hash(a), 16) >= 0


def test_frontmatter_keys():
    """U-REN-3: frontmatter 파싱, contentid 문자열, 출처·기준일·수정일시 키."""
    fm = frontmatter(render_entity(make_item()))
    assert fm["contentid"] == "126508"
    assert {"source", "as_of", "updated_at"} <= set(fm)


def test_title_with_quotes():
    """U-REN-4: 따옴표·콜론이 든 제목도 파싱되고 원문 그대로."""
    title = '경복궁: "정궁"'
    assert frontmatter(render_entity(make_item(title=title)))["title"] == title


def test_no_unicode_escape():
    """U-REN-5: 한글이 \\u 이스케이프되지 않는다."""
    text = render_entity(make_item())
    assert "\\u" not in text and "경복궁" in text


def test_missing_values_omitted():
    """U-REN-6: 값 없는 줄·빈 절 생략, 'None' 없음."""
    text = render_entity(make_item(tel=None, fee=None, restdate=None, extra={}))
    assert "전화:" not in text and "이용요금:" not in text and "휴무일:" not in text
    assert "## 개요" not in text and "None" not in text


def test_no_sigungu_key():
    """U-REN-7: sigungu_code None → frontmatter 키 없음."""
    assert "sigungu_code" not in frontmatter(render_entity(make_item(sigungu_code=None)))


def test_body_id_and_source_line():
    """U-REN-8: '관광지 ID' 줄, 마지막 출처 줄에 기준일."""
    lines = render_entity(make_item()).rstrip("\n").split("\n")
    assert "관광지 ID: 126508 · 유형: 관광지 · 지역: 서울" in lines
    assert lines[-1].startswith("출처:") and "2026-11-21" in lines[-1]


def test_entity_path():
    """U-REN-9: 경로 규칙."""
    assert entity_path(12, "126508") == "entity/12/126508.md"


def test_write_page_atomic(tmp_path):
    """U-REN-10: 두 번 쓰기 → 두 번째 내용, 임시 파일 없음, 중간 폴더 생성."""
    write_page(tmp_path, "entity/12/1.md", "x")
    p = write_page(tmp_path, "entity/12/1.md", "y")
    assert p.read_text(encoding="utf-8") == "y"
    assert [f.name for f in p.parent.iterdir()] == ["1.md"]


def test_updated_at_changes_hash():
    """U-REN-11: updated_at 1초 차이 → 해시가 달라진다."""
    a = render_entity(make_item())
    b = render_entity(make_item(updated_at=UPDATED + timedelta(seconds=1)))
    assert content_hash(a) != content_hash(b)
