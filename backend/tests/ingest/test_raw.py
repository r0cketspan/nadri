"""raw 스냅샷 단위테스트 (U-RAW)."""

import json
import os
from datetime import datetime, timezone

from nadri.core.tourapi import KST, TourApiResponse
from nadri.ingest.raw import save_raw


def resp(fetched_at: datetime, op: str = "detailCommon2") -> TourApiResponse:
    """한글 본문이 든 가짜 응답."""
    return TourApiResponse(op, {"contentId": "126508"}, {"title": "경복궁"}, [], 0, fetched_at)


def test_path_and_content(tmp_path):
    """U-RAW-1: 경로 규칙, 저장 키, 한글 그대로."""
    p = save_raw(tmp_path, resp(datetime(2026, 11, 21, 0, 30, tzinfo=KST)), "126508")
    assert p == tmp_path / "2026-11-21" / "detailCommon2" / "126508.json"
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    assert set(data) == {"operation", "params", "fetched_at", "body"}
    assert "경복궁" in text and "serviceKey" not in text


def test_kst_date_folder(tmp_path):
    """U-RAW-2: UTC 11-20 15:30 → KST 11-21 폴더."""
    p = save_raw(tmp_path, resp(datetime(2026, 11, 20, 15, 30, tzinfo=timezone.utc)), "126508")
    assert p.parent.parent.name == "2026-11-21"


def test_never_overwrites(tmp_path):
    """U-RAW-3·4: 같은 키 재저장 → .2.json, .3.json, 첫 파일 불변."""
    r = resp(datetime(2026, 11, 21, 10, 0, tzinfo=KST))
    first = save_raw(tmp_path, r, "126508")
    before = (first.read_bytes(), os.stat(first).st_mtime_ns)
    second = save_raw(tmp_path, r, "126508")
    third = save_raw(tmp_path, r, "126508")
    assert second.name == "126508.2.json" and third.name == "126508.3.json"
    assert (first.read_bytes(), os.stat(first).st_mtime_ns) == before


def test_unsafe_key(tmp_path):
    """U-RAW-5: 경로 구분자·공백 치환, 상위 폴더 탈출 없음."""
    p = save_raw(tmp_path, resp(datetime(2026, 11, 21, 10, 0, tzinfo=KST), "areaBasedList2"), "서울/12 p1")
    assert p.name == "서울_12_p1.json" and p.parent == tmp_path / "2026-11-21" / "areaBasedList2"
    p2 = save_raw(tmp_path, resp(datetime(2026, 11, 21, 10, 0, tzinfo=KST)), "../../etc")
    assert tmp_path in p2.parents
