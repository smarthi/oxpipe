from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from oxpipe.dashboard.html import DASHBOARD_HTML
from oxpipe.events.log import summarize_events
from oxpipe.runtime.state import CompressionBody, ModelsBody


async def dashboard_page(_: Request) -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)


async def api_state(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    snap = runtime.snapshot(settings.models)
    snap["summary"] = summarize_events(settings.events_path)
    snap["counterfactual"] = settings.counterfactual
    return JSONResponse(snap)


async def api_compression(request: Request) -> JSONResponse:
    runtime = request.app.state.runtime
    body = CompressionBody.model_validate(await request.json())
    runtime.set_compression(body.enabled)
    return JSONResponse({"ok": True, "compression_enabled": body.enabled})


async def api_models(request: Request) -> JSONResponse:
    runtime = request.app.state.runtime
    body = ModelsBody.model_validate(await request.json())
    runtime.set_models(body.models)
    return JSONResponse({"ok": True, "models": body.models})


async def api_events(request: Request) -> JSONResponse:
    runtime = request.app.state.runtime
    return JSONResponse({"events": list(runtime.recent)})
