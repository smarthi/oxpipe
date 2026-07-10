from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from oxpipe.config import Settings
from oxpipe.proxy.app import create_app


@pytest.mark.asyncio
async def test_dashboard_and_kill_switch():
    app = create_app(Settings(models=["gpt-5.6"], counterfactual=False))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "oxpipe" in r.text

        s = await client.get("/api/state")
        assert s.status_code == 200
        data = s.json()
        assert data["compression_enabled"] is True
        assert "gpt-5.6" in data["models"]

        off = await client.post("/api/compression", json={"enabled": False})
        assert off.json()["compression_enabled"] is False

        models = await client.post("/api/models", json={"models": ["gpt-5.5", "gpt-5.6"]})
        assert models.status_code == 200
        s2 = (await client.get("/api/state")).json()
        assert s2["compression_enabled"] is False
        assert s2["models"] == ["gpt-5.5", "gpt-5.6"]
