"""TourAPI 클라이언트 단위테스트 (U-TA) — httpx.MockTransport."""

from datetime import datetime

import httpx
import pytest

from nadri.core.tourapi import KST, TourApiClient, TourApiError, parse_response
from tests.conftest import load_fixture

KEY = "TEST-SERVICE-KEY-1234"
BASE = "https://apis.data.go.kr/B551011/KorService2"


def make_client(handler, on_call=None) -> TourApiClient:
    """MockTransport로 응답을 흉내 내는 클라이언트."""
    return TourApiClient(
        KEY, BASE, transport=httpx.MockTransport(handler), on_call=on_call,
        clock=lambda: datetime(2026, 11, 21, 10, 0, tzinfo=KST),
    )


def test_parse_list():
    """U-TA-1: item 리스트 3개, totalCount 120."""
    body, items, total = parse_response("areaBasedList2", 200, load_fixture("tourapi/list_seoul_12.json"))
    assert len(items) == 3 and total == 120 and body["response"]["header"]["resultCode"] == "0000"


def test_parse_single_item_dict():
    """U-TA-2: item이 dict 하나면 원소 1개 리스트."""
    _, items, _ = parse_response("areaBasedList2", 200, load_fixture("tourapi/list_single.json"))
    assert items == [items[0]] and items[0]["contentid"] == "126508"


def test_parse_empty_items():
    """U-TA-3: items "" → [], totalCount 0."""
    _, items, total = parse_response("areaBasedList2", 200, load_fixture("tourapi/list_empty.json"))
    assert items == [] and total == 0


def test_parse_quota_error():
    """U-TA-4: resultCode 22 → quota_exceeded."""
    with pytest.raises(TourApiError) as e:
        parse_response("detailCommon2", 200, load_fixture("tourapi/error_22.json"))
    assert e.value.code == "22" and e.value.quota_exceeded is True and e.value.rate_limited is False


def test_parse_gateway_xml():
    """U-TA-5: 게이트웨이 XML 오류 → returnReasonCode."""
    with pytest.raises(TourApiError) as e:
        parse_response("detailCommon2", 200, load_fixture("tourapi/gateway_30.xml"))
    assert e.value.code == "30"


def test_parse_gateway_rate():
    """U-TA-6: XML 코드 23 → rate_limited."""
    with pytest.raises(TourApiError) as e:
        parse_response("detailCommon2", 200, load_fixture("tourapi/gateway_23.xml"))
    assert e.value.rate_limited is True


def test_parse_http_500():
    """U-TA-7: HTTP 500 → http_500."""
    with pytest.raises(TourApiError) as e:
        parse_response("detailCommon2", 500, "")
    assert e.value.code == "http_500"


def test_parse_broken_body():
    """U-TA-8: 해석 불가 본문 → parse."""
    with pytest.raises(TourApiError) as e:
        parse_response("detailCommon2", 200, "<html>오류")
    assert e.value.code == "parse"


async def test_area_based_list_request():
    """U-TA-9 · U-TA-11: 목록 요청 쿼리·경로, 반환 params에 serviceKey 없음."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        """요청을 기록하거나 검사하고 가짜 응답을 돌려준다."""
        seen.append(req)
        return httpx.Response(200, text=load_fixture("tourapi/list_seoul_12.json"))

    client = make_client(handler)
    resp = await client.area_based_list("서울", 12, num_of_rows=30)
    q = seen[0].url.params
    assert seen[0].url.path.endswith("/areaBasedList2")
    assert (q["areaCode"], q["contentTypeId"], q["numOfRows"], q["pageNo"]) == ("1", "12", "30", "1")
    assert (q["_type"], q["MobileOS"], q["MobileApp"]) == ("json", "ETC", "nadri")
    assert q["serviceKey"] == KEY
    assert "serviceKey" not in resp.params
    assert resp.total_count == 120 and resp.fetched_at.tzinfo is not None
    await client.aclose()


async def test_detail_intro_request():
    """U-TA-10: detailIntro2 경로·contentId·contentTypeId."""
    seen = []

    def handler(req):
        """요청을 기록하거나 검사하고 가짜 응답을 돌려준다."""
        seen.append(req)
        return httpx.Response(200, text=load_fixture("tourapi/intro_126508.json"))

    client = make_client(handler)
    resp = await client.detail_intro("126508", 12)
    assert seen[0].url.path.endswith("/detailIntro2")
    assert seen[0].url.params["contentId"] == "126508" and seen[0].url.params["contentTypeId"] == "12"
    assert "serviceKey" not in resp.params
    await client.aclose()


async def test_on_call_counts_errors_too():
    """U-TA-12: 성공 1회 + 오류(22) 1회 → 콜백 2회, 인자는 오퍼레이션 이름."""
    calls = []
    bodies = iter([load_fixture("tourapi/common_126508.json"), load_fixture("tourapi/error_22.json")])

    async def on_call(op):
        calls.append(op)

    client = make_client(lambda req: httpx.Response(200, text=next(bodies)), on_call=on_call)
    await client.detail_common("126508")
    with pytest.raises(TourApiError):
        await client.detail_common("126508")
    assert calls == ["detailCommon2", "detailCommon2"] and client.calls == 2
    await client.aclose()


async def test_timeout_no_retry():
    """U-TA-13: 타임아웃 → code timeout, 요청 1회(재시도 없음)."""
    n = []

    def handler(req):
        """요청을 기록하거나 검사하고 가짜 응답을 돌려준다."""
        n.append(req)
        raise httpx.ReadTimeout("느림", request=req)

    client = make_client(handler)
    with pytest.raises(TourApiError) as e:
        await client.detail_common("126508")
    assert e.value.code == "timeout" and len(n) == 1
    await client.aclose()


async def test_error_message_hides_key():
    """U-TA-14: 오류 30 예외 문자열에 서비스 키가 없다."""
    client = make_client(lambda req: httpx.Response(200, text=load_fixture("tourapi/gateway_30.xml")))
    with pytest.raises(TourApiError) as e:
        await client.detail_common("126508")
    assert KEY not in str(e.value) and KEY not in repr(e.value)
    await client.aclose()


async def test_unknown_area_no_call():
    """U-TA-15: 모르는 지역 → ValueError, HTTP 호출 없음."""
    n = []
    client = make_client(lambda req: n.append(req) or httpx.Response(200))
    with pytest.raises(ValueError):
        await client.area_based_list("부산", 12, num_of_rows=1)
    assert n == []
    await client.aclose()
