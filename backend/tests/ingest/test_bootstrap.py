"""적재 보조 함수 단위테스트 (U-BS). run_bootstrap 전체 흐름은 통합 테스트·HITL에서 본다."""

import json

import httpx
import pytest

from nadri.core.tourapi import AREAS, CONTENT_TYPES, TourApiClient
from nadri.ingest.bootstrap import budget_allows, count_totals, estimate_calls, estimate_days, validate_args


def test_estimate_calls():
    """U-BS-1: 목록 1 + 상세 3 × limit."""
    assert [estimate_calls(n) for n in (30, 20, 1)] == [91, 61, 4]


def test_budget_allows():
    """U-BS-2: 사용량 + 예상 ≤ 예산."""
    assert budget_allows(0, 91, 800) is True
    assert budget_allows(710, 91, 800) is False
    assert budget_allows(709, 91, 800) is True


@pytest.mark.parametrize("area,t,limit", [("부산", 12, 1), ("서울", 14, 1), ("서울", 12, 0), ("서울", 12, 51)])
def test_validate_args(area, t, limit):
    """U-BS-3: 지역·유형·건수 범위 밖 → ValueError(호출 전 검사라 TourAPI 호출 없음)."""
    with pytest.raises(ValueError):
        validate_args(area, t, limit)


async def test_count_totals():
    """U-BS-4: 16칸, 16호출, 모두 numOfRows=1."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        """요청을 기록하거나 검사하고 가짜 응답을 돌려준다."""
        seen.append(req.url.params)
        total = int(req.url.params["contentTypeId"]) * (1 if req.url.params["areaCode"] == "1" else 2)
        body = {"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                             "body": {"items": "", "totalCount": total}}}
        return httpx.Response(200, text=json.dumps(body))

    client = TourApiClient("k", "https://x/KorService2", transport=httpx.MockTransport(handler))
    totals = await count_totals(client, list(AREAS), list(CONTENT_TYPES))
    await client.aclose()
    assert len(totals) == 16 and len(seen) == 16
    assert all(p["numOfRows"] == "1" for p in seen)
    assert totals[("서울", 12)] == 12 and totals[("제주", 39)] == 78


def test_estimate_days():
    """U-BS-5: 한 칸 3,000 → 서비스 전체 12일, 오퍼레이션별 4일."""
    totals = {(a, t): 0 for a in AREAS for t in CONTENT_TYPES}
    totals[("서울", 12)] = 3000
    assert estimate_days(totals, 800) == {"service_wide": 12, "per_operation": 4}
