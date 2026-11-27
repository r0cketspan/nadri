"""통합: 버전·어댑터 툴 목록·호출·인증 (I-1~I-4)."""

from datetime import datetime
from importlib.metadata import version

import httpx
import pytest
from sqlalchemy import select

from nadri.core.db import create_engine, session_factory
from nadri.core.models.tour import TourItem
from nadri.core.tourapi import KST
from tests.integration.conftest import as_json

pytestmark = pytest.mark.integration


def adapter(settings):
    """토큰 헤더를 넣은 어댑터 클라이언트."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    return MultiServerMCPClient({"tour": {
        "transport": "streamable_http",
        "url": settings.tools_url,
        "headers": {"Authorization": f"Bearer {settings.tools_api_key.get_secret_value()}"},
    }})


def test_versions():
    """I-1: mcp 1.30.0, langchain-mcp-adapters 0.3.2 (A21)."""
    assert version("mcp") == "1.30.0"
    assert version("langchain-mcp-adapters") == "0.3.2"


async def test_tool_list(app_settings):
    """I-2: 툴 3종과 입력 스키마."""
    tools = await adapter(app_settings).get_tools()
    assert {t.name for t in tools} == {"rag_query", "data_query", "get_datetime"}
    assert all(t.args_schema is not None for t in tools)


async def test_tool_calls(app_settings):
    """I-3: rag_query·data_query·get_datetime 실제 호출."""
    tools = {t.name: t for t in await adapter(app_settings).get_tools()}

    # rag_query: 1~5개, contentid가 tour_items에 있음, 출처·기준일
    rag = as_json(await tools["rag_query"].ainvoke({"question": "경복궁 관람 시간"}))
    assert 1 <= rag["count"] <= 5
    engine = create_engine(app_settings)
    async with session_factory(engine)() as s:
        ids = set((await s.execute(select(TourItem.contentid))).scalars())
    await engine.dispose()
    for item in rag["items"]:
        assert item["contentid"] in ids and item["source"] and item["as_of"]

    # data_query: 제주 20개 이하·전부 제주
    dq = as_json(await tools["data_query"].ainvoke({"area": "제주", "limit": 30}))
    assert dq["count"] <= 20 and all(i["area"] == "제주" for i in dq["items"])

    # get_datetime: 오늘 KST 날짜
    dt = as_json(await tools["get_datetime"].ainvoke({}))
    assert dt["date"] == datetime.now(KST).date().isoformat()


async def test_auth(app_settings):
    """I-4: 토큰 없음·틀림 401, GET /health 200."""
    url = app_settings.tools_url
    async with httpx.AsyncClient() as c:
        assert (await c.post(url)).status_code == 401
        assert (await c.post(url, headers={"Authorization": "Bearer wrong"})).status_code == 401
        assert (await c.get(url.rsplit("/mcp", 1)[0] + "/health")).status_code == 200
