from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from starlette.applications import Starlette
from starlette.routing import Route

from oxpipe.config import Settings
from oxpipe.dashboard.routes import (
    api_compression,
    api_events,
    api_models,
    api_state,
    dashboard_page,
)
from oxpipe.proxy.routes import handle_openai_proxy, health
from oxpipe.runtime.state import RuntimeState


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings()
    runtime = RuntimeState(initial_models=settings.models)

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.http = httpx.AsyncClient(timeout=None, follow_redirects=True)
        try:
            yield
        finally:
            await app.state.http.aclose()

    app = Starlette(
        routes=[
            Route("/", dashboard_page, methods=["GET"]),
            Route("/dashboard", dashboard_page, methods=["GET"]),
            Route("/api/state", api_state, methods=["GET"]),
            Route("/api/events", api_events, methods=["GET"]),
            Route("/api/compression", api_compression, methods=["POST"]),
            Route("/api/models", api_models, methods=["POST"]),
            Route("/healthz", health, methods=["GET"]),
            Route("/v1/{path:path}", handle_openai_proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
            Route("/{path:path}", handle_openai_proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        ],
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.runtime = runtime
    return app
