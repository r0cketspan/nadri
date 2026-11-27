"""MCP 인증 미들웨어 단위테스트 (U-AUTH)."""

import httpx
import pytest

from nadri.tools.server import BearerAuthMiddleware, build_app
from tests.conftest import make_settings


class DummyApp:
    """200 ok를 돌려주고 호출 여부를 기록하는 ASGI 앱."""

    def __init__(self):
        """호출 횟수·스코프 종류 기록을 비운다."""
        self.called = 0
        self.scopes = []

    async def __call__(self, scope, receive, send):
        """http면 200 ok, 그 외 스코프는 기록만."""
        self.called += 1
        self.scopes.append(scope["type"])
        if scope["type"] != "http":
            return
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"ok"})


async def call(method: str, path: str, headers: dict | None = None):
    """미들웨어로 감싼 더미 앱에 요청 하나를 보낸다."""
    app = DummyApp()
    transport = httpx.ASGITransport(app=BearerAuthMiddleware(app, token="t0k"))
    async with httpx.AsyncClient(transport=transport, base_url="http://tour-tools:8000") as c:
        resp = await c.request(method, path, headers=headers or {})
    return resp, app


@pytest.mark.parametrize("headers", [
    {},                                   # U-AUTH-1 헤더 없음
    {"Authorization": "Bearer wrong"},    # U-AUTH-2 틀린 토큰
    {"Authorization": "t0k"},             # U-AUTH-3 접두어 없음
    {"Authorization": "bearer t0k"},      # U-AUTH-4 소문자 접두어
])
async def test_rejected(headers):
    """U-AUTH-1~4: 401, 같은 본문, 내부 앱 호출 안 됨."""
    resp, app = await call("POST", "/mcp", headers)
    assert resp.status_code == 401 and resp.json() == {"error": "unauthorized"} and app.called == 0


async def test_valid_token():
    """U-AUTH-5: 정확한 토큰 → 200 ok."""
    resp, app = await call("POST", "/mcp", {"Authorization": "Bearer t0k"})
    assert resp.status_code == 200 and resp.text == "ok" and app.called == 1


async def test_health_without_token():
    """U-AUTH-6: GET /health 는 토큰 없이 200, 내부 앱 호출 안 됨."""
    resp, app = await call("GET", "/health")
    assert resp.status_code == 200 and resp.text == "ok" and app.called == 0


async def test_post_health_needs_token():
    """U-AUTH-7: POST /health 는 예외 아님 → 401."""
    resp, _ = await call("POST", "/health")
    assert resp.status_code == 401


async def test_lifespan_passthrough():
    """U-AUTH-8: lifespan 스코프는 그대로 전달."""
    app = DummyApp()

    async def noop(*_):
        """receive·send 자리 채움."""
        return None

    await BearerAuthMiddleware(app, token="t0k")({"type": "lifespan"}, noop, noop)
    assert app.scopes == ["lifespan"]


def test_build_app_rejects_empty_token():
    """U-AUTH-9: 빈 토큰이면 기동 거부(리랭커 로드 전)."""
    with pytest.raises(RuntimeError):
        build_app(make_settings(tools_api_key=""))
    with pytest.raises(RuntimeError):
        build_app(make_settings(tools_api_key=None))
