from __future__ import annotations

import httpx
from starlette.applications import Starlette
from starlette.routing import Route

from oxpipe.config import Settings
from oxpipe.proxy.routes import handle_openai_proxy, health


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings()

    async def on_startup() -> None:
        app.state.http = httpx.AsyncClient(timeout=None, follow_redirects=True)

    async def on_shutdown() -> None:
        client: httpx.AsyncClient = app.state.http
        await client.aclose()

    app = Starlette(
        routes=[
            Route("/healthz", health, methods=["GET"]),
            Route("/v1/{path:path}", handle_openai_proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
            Route("/{path:path}", handle_openai_proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        ],
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
    )
    app.state.settings = settings
    return app
