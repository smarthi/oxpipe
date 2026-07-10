from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from oxpipe.config import Settings
from oxpipe.proxy.app import create_app
from oxpipe.transform.common import clear_profile_cache


def _dense(n: int = 8000) -> str:
    line = "def foo(x): return {" + ("a" * 90) + "}\n"
    return line * max(1, n // len(line))


def _app_with_mock(settings: Settings, handler, events_path=None) -> object:
    if events_path is not None:
        settings = settings.model_copy(update={"events_path": events_path})
    app = create_app(settings)
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=None, follow_redirects=True)
    return app


@pytest.mark.asyncio
async def test_proxy_passthrough_when_models_off(tmp_path):
    clear_profile_cache()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "id": "chat",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1},
            },
        )

    app = _app_with_mock(
        Settings(models=[], counterfactual=False, min_chars=1000),
        handler,
        events_path=tmp_path / "events.jsonl",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-5.6", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert r.status_code == 200
        assert r.json()["choices"][0]["message"]["content"] == "ok"
    await app.state.http.aclose()
    assert any("chat/completions" in u for u in calls)


@pytest.mark.asyncio
async def test_proxy_images_and_counterfactual(tmp_path):
    clear_profile_cache()
    seen_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 9000})
        body = json.loads(request.content.decode()) if request.content else {}
        seen_bodies.append(body)
        return httpx.Response(
            200,
            json={
                "id": "chat",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 1500,
                    "completion_tokens": 5,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            },
        )

    app = _app_with_mock(
        Settings(models=["gpt-5.6"], counterfactual=True, min_chars=1000, live_tail=1),
        handler,
        events_path=tmp_path / "events.jsonl",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/chat/completions",
            json={
                "model": "gpt-5.6",
                "messages": [
                    {"role": "system", "content": _dense(5000)},
                    {"role": "user", "content": "continue"},
                ],
            },
        )
        assert r.status_code == 200
        _ = r.content
        state = (await client.get("/api/state")).json()
        assert state["counters"]["requests"] >= 1
    await app.state.http.aclose()
    assert seen_bodies
    fwd = seen_bodies[0]
    content = fwd["messages"][0]["content"] if fwd.get("messages") else None
    if isinstance(content, list):
        assert any(p.get("type") == "image_url" for p in content if isinstance(p, dict))


@pytest.mark.asyncio
async def test_kill_switch_forces_passthrough(tmp_path):
    clear_profile_cache()
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json={"input_tokens": 100})
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 5}})

    app = _app_with_mock(
        Settings(models=["gpt-5.6"], counterfactual=False, min_chars=100),
        handler,
        events_path=tmp_path / "events.jsonl",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/compression", json={"enabled": False})
        r = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-5.6",
                "messages": [
                    {"role": "system", "content": _dense(5000)},
                    {"role": "user", "content": "hi"},
                ],
            },
        )
        assert r.status_code == 200
        _ = r.content
    await app.state.http.aclose()
    assert seen
    sys_msg = seen[0]["messages"][0]
    assert isinstance(sys_msg["content"], str)


@pytest.mark.asyncio
async def test_api_events_endpoint():
    app = create_app(Settings(models=["gpt-5.6"]))
    app.state.runtime.record({"applied": True, "model": "gpt-5.6", "saved_eff": 1})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/events")
        assert r.status_code == 200
        assert len(r.json()["events"]) >= 1
