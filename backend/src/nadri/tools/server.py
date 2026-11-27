"""tour-tools MCP 서버 — FastMCP(stateless Streamable HTTP) + Bearer 토큰 미들웨어 + 툴 3종."""

import hmac
import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp, Receive, Scope, Send

from nadri.core.config import Settings, get_settings
from nadri.core.db import create_engine, session_factory
from nadri.tools.data_query import DataQueryParams, NearPoint, data_query
from nadri.tools.get_datetime import get_datetime
from nadri.tools.rag_query import rag_query
from nadri.tools.reranker import CrossEncoderReranker

log = logging.getLogger(__name__)


@dataclass
class ToolDeps:
    """툴 함수가 쓰는 공유 자원(서버 기동 시 1회 생성)."""

    settings: Settings
    sf: async_sessionmaker[AsyncSession]  # nadri_tools 롤
    lightrag_http: httpx.AsyncClient
    reranker: CrossEncoderReranker


class BearerAuthMiddleware:
    """Authorization: Bearer <TOOLS_API_KEY>가 맞을 때만 내부 앱으로 넘기는 순수 ASGI 미들웨어."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        """
        Args:
            app: 감쌀 앱(FastMCP streamable_http_app)
            token: 기대하는 토큰(빈 값 금지 — build_app이 검사)
        """
        self.app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        요청 하나를 검사한다.

        규칙: http 외(lifespan 등) → 통과 / GET /health → 토큰 없이 200 ok /
        그 외 → 헤더가 정확히 'Bearer <token>'이면 통과, 아니면 401(이유 구분 없음).
        """
        # 1) lifespan 등 http가 아닌 스코프는 그대로 넘긴다(세션 매니저 기동에 필요)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # 2) 헬스체크 전용 경로 — 다른 정보는 주지 않는다
        if scope["method"] == "GET" and scope["path"] == "/health":
            await _respond(send, 200, b"ok", b"text/plain")
            return
        # 3) 토큰 비교(상수 시간)
        header = dict(scope.get("headers") or []).get(b"authorization", b"")
        if hmac.compare_digest(header, self._expected):
            await self.app(scope, receive, send)
            return
        await _respond(send, 401, json.dumps({"error": "unauthorized"}).encode(), b"application/json")


async def _respond(send: Send, status: int, body: bytes, content_type: bytes) -> None:
    """짧은 HTTP 응답을 직접 보낸다."""
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", content_type), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})


def build_mcp(deps: ToolDeps) -> FastMCP:
    """
    FastMCP('nadri-tour-tools', stateless_http=True)에 rag_query·data_query·get_datetime을 등록한다.

    툴 설명(래퍼 docstring)은 LLM이 보는 고정 문자열이다.

    Args:
        deps: 툴이 쓰는 공유 자원

    Returns:
        툴이 등록된 FastMCP
    """
    # host를 0.0.0.0으로 두는 이유: 기본값(127.0.0.1)이면 DNS 리바인딩 보호가 켜져
    # 컨테이너 이름(tour-tools:8000)으로 온 요청이 거부된다. 접근 통제는 Bearer 토큰이 맡는다.
    mcp = FastMCP("nadri-tour-tools", stateless_http=True, host="0.0.0.0")

    @mcp.tool(name="rag_query")
    async def rag_query_tool(question: str) -> dict:
        """관광 위키에서 질문과 관련된 문단을 찾아 정확도 순 최대 5개를 돌려준다. 각 항목에 contentid·출처·기준일이 있다. 장소 설명·특징·이용 안내 같은 서술형 질문에 쓴다."""
        return await rag_query(question, deps)

    @mcp.tool(name="data_query")
    async def data_query_tool(
        area: Literal["서울", "제주"],
        sigungu_code: str | None = None,
        content_type: Literal[12, 14, 15, 25, 28, 32, 38, 39] | None = None,
        keyword: str | None = None,
        near: NearPoint | None = None,
        on_date: date | None = None,
        sort: Literal["title", "distance", "modified"] = "title",
        limit: int = 10,
    ) -> dict:
        """관광 정보 DB를 조건으로 조회한다. area(서울/제주) 필수. content_type: 12 관광지·14 문화시설·15 축제공연행사·25 여행코스·28 레포츠·32 숙박·38 쇼핑·39 음식점. keyword는 이름·주소 부분 일치, near는 좌표 반경(km, 최대 20) 검색, on_date는 그날 진행 중인 행사, limit 최대 20."""
        params = DataQueryParams(
            area=area, sigungu_code=sigungu_code, content_type=content_type, keyword=keyword,
            near=near, on_date=on_date, sort=sort, limit=limit,
        )
        return await data_query(params, deps)

    @mcp.tool(name="get_datetime")
    async def get_datetime_tool() -> dict:
        """현재 한국 시각·날짜·요일과 '이번 주말'(이번 주 토~일, 일요일이면 어제~오늘)·'다음 주'(다음 월~일) 날짜 범위를 돌려준다."""
        return await get_datetime()

    return mcp


def build_app(settings: Settings | None = None) -> ASGIApp:
    """
    설정을 읽어 ToolDeps·FastMCP를 만들고 streamable_http_app()을 인증 미들웨어로 감싼다(uvicorn --factory용).

    Args:
        settings: 테스트용 설정(기본은 환경변수)

    Returns:
        인증 미들웨어로 감싼 ASGI 앱

    Raises:
        RuntimeError: TOOLS_API_KEY가 비어 있음(인증 없이 기동하지 않음)
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if settings is None:
        try:
            settings = get_settings()
        except ValidationError as e:
            # 입력값(비밀번호 등)이 로그에 남지 않게 필드 이름만 알린다
            fields = ", ".join(str(err["loc"][0]).upper() for err in e.errors())
            raise RuntimeError(f"설정 오류: 환경변수 확인 필요 — {fields}") from None
    # 1) 토큰이 없으면 기동을 거부한다(무인증 MCP 서버 방지)
    token = settings.tools_api_key.get_secret_value() if settings.tools_api_key else ""
    if not token:
        raise RuntimeError("TOOLS_API_KEY가 비어 있어 tour-tools를 기동하지 않습니다")
    lightrag_key = settings.lightrag_api_key.get_secret_value() if settings.lightrag_api_key else ""

    # 2) 공유 자원: DB 세션 팩토리(nadri_tools), LightRAG 클라이언트, 리랭커(여기서 1회 로드)
    deps = ToolDeps(
        settings=settings,
        sf=session_factory(create_engine(settings)),
        lightrag_http=httpx.AsyncClient(base_url=settings.lightrag_url, headers={"X-API-Key": lightrag_key}),
        reranker=CrossEncoderReranker(settings.reranker_model_path, settings.reranker_max_length),
    )
    # 3) MCP 앱을 인증 미들웨어로 감싼다
    return BearerAuthMiddleware(build_mcp(deps).streamable_http_app(), token)


def main() -> None:
    """리랭커를 미리 올린 뒤(build_app 안에서) uvicorn으로 0.0.0.0:8000에서 서비스한다."""
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
