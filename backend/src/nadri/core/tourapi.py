"""한국관광공사 TourAPI 4.0(KorService2) 비동기 클라이언트 — 목록·상세 3종 호출과 응답 해석."""

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

KST = ZoneInfo("Asia/Seoul")
# 지역 → 목록 조회 파라미터. KorService2는 법정동 시도 코드(lDongRegnCd)로 지역을 찾는다
# (2026-11-28 실호출 확인: areaCode=1은 서울 관광지 17건만, lDongRegnCd=11은 768건).
AREAS: dict[str, dict[str, str]] = {"서울": {"lDongRegnCd": "11"}, "제주": {"lDongRegnCd": "50"}}
CONTENT_TYPES: dict[int, str] = {
    12: "관광지", 14: "문화시설", 15: "축제공연행사", 25: "여행코스",
    28: "레포츠", 32: "숙박", 38: "쇼핑", 39: "음식점",
}
QUOTA_CODES = {"22"}  # 일일 한도 초과
RATE_CODES = {"23"}  # 초당 한도 초과

# 모든 호출에 붙는 공통 파라미터(serviceKey 제외)
_COMMON_PARAMS = {"MobileOS": "ETC", "MobileApp": "nadri", "_type": "json"}
# 게이트웨이 XML 오류 본문에서 코드·메시지를 뽑는 정규식
_XML_CODE = re.compile(r"<returnReasonCode>\s*([^<\s]+)\s*</returnReasonCode>")
_XML_MSG = re.compile(r"<returnAuthMsg>\s*([^<]*?)\s*</returnAuthMsg>")


class TourApiError(Exception):
    """
    TourAPI 호출 실패.

    code는 공공데이터포털 resultCode/returnReasonCode, 또는 'http_<상태>'·'timeout'·'parse'.
    메시지에는 서비스 키·요청 URL을 넣지 않는다.
    """

    def __init__(self, code: str, message: str = "") -> None:
        """
        Args:
            code: 오류 코드
            message: 사람이 읽을 짧은 설명(비밀값 없음)
        """
        super().__init__(f"TourAPI 오류 {code}: {message}" if message else f"TourAPI 오류 {code}")
        self.code = code
        self.message = message

    @property
    def quota_exceeded(self) -> bool:
        """일일 호출 한도 초과(22)이면 True."""
        return self.code in QUOTA_CODES

    @property
    def rate_limited(self) -> bool:
        """초당 호출 한도 초과(23)이면 True."""
        return self.code in RATE_CODES


@dataclass(frozen=True)
class TourApiResponse:
    """한 번의 TourAPI 호출 결과. body는 raw 저장용 원본, params에는 serviceKey가 없다."""

    operation: str
    params: dict[str, str]
    body: dict
    items: list[dict]
    total_count: int
    fetched_at: datetime  # KST tz-aware


def parse_response(operation: str, status_code: int, text: str) -> tuple[dict, list[dict], int]:
    """
    응답 본문을 해석해 (원본 dict, item 목록, totalCount)를 돌려준다.

    Args:
        operation: 오퍼레이션 이름(오류 메시지용)
        status_code: HTTP 상태 코드
        text: 응답 본문 문자열

    Returns:
        (JSON 원본, item dict 목록, totalCount)

    Raises:
        TourApiError: HTTP 오류·게이트웨이 XML 오류·resultCode 오류·해석 불가
    """
    # 1) HTTP 상태가 200이 아니면 바로 실패
    if status_code != 200:
        raise TourApiError(f"http_{status_code}", operation)

    # 2) 게이트웨이 오류는 JSON 요청에도 XML로 온다 — 코드를 정규식으로 뽑는다
    stripped = text.lstrip()
    if stripped.startswith("<"):
        code = _XML_CODE.search(text)
        if code is None:
            raise TourApiError("parse", f"{operation} 응답을 해석할 수 없습니다")
        msg = _XML_MSG.search(text)
        raise TourApiError(code.group(1), msg.group(1) if msg else "")

    # 3) JSON 해석 후 resultCode 확인
    try:
        body = json.loads(text)
        header = body["response"]["header"]
        resp_body = body["response"].get("body") or {}
    except (ValueError, KeyError, TypeError):
        raise TourApiError("parse", f"{operation} 응답을 해석할 수 없습니다") from None
    result_code = str(header.get("resultCode", ""))
    if result_code != "0000":
        raise TourApiError(result_code or "parse", str(header.get("resultMsg", "")))

    # 4) items 정규화: "" 또는 없음 → [], dict 하나 → [dict]
    items_node = resp_body.get("items")
    raw_items = items_node.get("item") if isinstance(items_node, dict) else None
    if raw_items is None:
        items: list[dict] = []
    elif isinstance(raw_items, dict):
        items = [raw_items]
    else:
        items = list(raw_items)

    # 5) totalCount가 없으면 0
    total = int(resp_body.get("totalCount") or 0)
    return body, items, total


class TourApiClient:
    """KorService2 비동기 클라이언트. 호출 1회마다 on_call 콜백으로 호출 수를 알린다. 자동 재시도는 하지 않는다."""

    def __init__(
        self,
        service_key: str,
        base_url: str,
        *,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        on_call: Callable[[str], Awaitable[None]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(KST),
    ) -> None:
        """
        Args:
            service_key: 공공데이터포털 Decoding 인증키(httpx가 쿼리 인코딩을 함)
            base_url: KorService2 기본 URL
            timeout: 요청 타임아웃(초)
            transport: 테스트용 httpx 전송 계층
            on_call: 요청을 보낸 직후 오퍼레이션 이름으로 호출되는 콜백(호출 수 기록)
            clock: 응답 시각을 정하는 시계(테스트 주입용)
        """
        self._key = service_key
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", timeout=timeout, transport=transport)
        self._on_call = on_call
        self._clock = clock
        self.calls = 0  # 이 클라이언트로 보낸 요청 수(실행 요약용)

    async def _call(self, operation: str, params: dict[str, str]) -> TourApiResponse:
        """
        오퍼레이션 하나를 호출하고 해석한다.

        Args:
            operation: 예) 'areaBasedList2'
            params: 오퍼레이션별 파라미터(serviceKey·공통 파라미터 제외)

        Returns:
            해석된 TourApiResponse (params에는 serviceKey 없음)

        Raises:
            TourApiError: 타임아웃·네트워크·응답 오류
        """
        # 1) 공통 파라미터를 붙인다 — serviceKey는 실제 요청에만 넣는다
        public_params = {**_COMMON_PARAMS, **params}
        try:
            resp = await self._http.get(operation, params={"serviceKey": self._key, **public_params})
        except httpx.TimeoutException:
            # 타임아웃도 포털에 잡혔을 수 있어 보수적으로 센다
            await self._notify(operation)
            raise TourApiError("timeout", operation) from None
        except httpx.HTTPError as e:
            raise TourApiError("network", f"{operation} {type(e).__name__}") from None

        # 2) 요청을 보냈으면 성공 여부와 무관하게 호출 수를 기록한다
        await self._notify(operation)

        # 3) 본문 해석(오류면 TourApiError)
        body, items, total = parse_response(operation, resp.status_code, resp.text)
        return TourApiResponse(operation, public_params, body, items, total, self._clock())

    async def _notify(self, operation: str) -> None:
        """보낸 요청 수를 세고, on_call 콜백이 있으면 부른다."""
        self.calls += 1
        if self._on_call is not None:
            await self._on_call(operation)

    async def area_based_list(
        self, area: str, content_type_id: int, *, num_of_rows: int, page_no: int = 1
    ) -> TourApiResponse:
        """
        지역·유형별 목록(areaBasedList2)을 수정일순으로 가져온다.

        Args:
            area: '서울' 또는 '제주'
            content_type_id: 관광 유형 코드
            num_of_rows: 한 페이지 건수
            page_no: 페이지 번호(1부터)

        Returns:
            목록 응답

        Raises:
            ValueError: 모르는 지역(HTTP 호출 없음)
            TourApiError: 호출 실패
        """
        # 1) 지역 이름을 TourAPI 코드로 바꾼다
        if area not in AREAS:
            raise ValueError(f"지원하지 않는 지역입니다: {area}")
        # 2) arrange=C(수정일순)로 목록을 요청한다
        params = {
            **AREAS[area],
            "contentTypeId": str(content_type_id),
            "numOfRows": str(num_of_rows),
            "pageNo": str(page_no),
            "arrange": "C",
        }
        return await self._call("areaBasedList2", params)

    async def detail_common(self, contentid: str) -> TourApiResponse:
        """공통 상세(detailCommon2 — 제목·주소·좌표·개요 등)를 가져온다."""
        return await self._call("detailCommon2", {"contentId": contentid})

    async def detail_intro(self, contentid: str, content_type_id: int) -> TourApiResponse:
        """유형별 소개 상세(detailIntro2 — 이용시간·휴무일 등)를 가져온다."""
        return await self._call("detailIntro2", {"contentId": contentid, "contentTypeId": str(content_type_id)})

    async def detail_info(self, contentid: str, content_type_id: int) -> TourApiResponse:
        """반복 정보 상세(detailInfo2 — 입장료 등 이름/값 목록)를 가져온다."""
        return await self._call("detailInfo2", {"contentId": contentid, "contentTypeId": str(content_type_id)})

    async def aclose(self) -> None:
        """HTTP 연결을 닫는다."""
        await self._http.aclose()
