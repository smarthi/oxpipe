from __future__ import annotations

import json
import time
import traceback
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from oxpipe.config import Settings
from oxpipe.events.log import append_event
from oxpipe.proxy.upstream import filter_request_headers, forward_stream, read_body
from oxpipe.transform.chat import transform_chat
from oxpipe.transform.responses import transform_responses


def _normalize_path(path: str) -> str:
    """Map client paths to OpenAI /v1/... form."""
    if not path.startswith("/"):
        path = "/" + path
    if path in {"/", ""}:
        return "/v1"
    if path.startswith("/v1/") or path == "/v1":
        return path
    # OPENAI_BASE_URL=.../v1 → client calls /chat/completions
    return "/v1" + path


async def handle_openai_proxy(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    client = request.app.state.http
    path = _normalize_path(request.url.path)
    upstream_url = f"{settings.upstream}{path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    raw = await read_body(request)
    headers = filter_request_headers(dict(request.headers))
    # Ensure Accept for SSE
    headers.setdefault("Accept", "application/json")

    applied = False
    reason = "passthrough"
    model = None
    pages = 0
    baseline_tokens = 0
    image_tokens_est = 0
    t0 = time.perf_counter()
    out_body = raw

    should_transform = request.method.upper() == "POST" and path in {
        "/v1/responses",
        "/v1/chat/completions",
    }

    if should_transform and raw:
        try:
            body: dict[str, Any] = json.loads(raw)
            model = body.get("model")
            if path == "/v1/responses":
                result = transform_responses(body, settings)
            else:
                result = transform_chat(body, settings)
            applied = result.applied
            reason = result.reason
            pages = result.pages
            baseline_tokens = result.baseline_tokens
            image_tokens_est = result.image_tokens_est
            if result.applied:
                out_body = json.dumps(result.body).encode("utf-8")
                headers["content-type"] = "application/json"
            elif result.reason in {"not_profitable", "below_min_chars"}:
                # still log
                pass
        except Exception as exc:  # fail open
            applied = False
            reason = f"transform_error:{type(exc).__name__}"
            out_body = raw
            # keep going with original

    latency_ms = int((time.perf_counter() - t0) * 1000)

    if should_transform and (applied or reason not in {"passthrough", "model_not_allowlisted"}):
        try:
            append_event(
                settings.events_path,
                {
                    "path": path,
                    "model": model,
                    "applied": applied,
                    "reason": reason,
                    "baseline_tokens": baseline_tokens,
                    "image_tokens_est": image_tokens_est,
                    "pages": pages,
                    "latency_ms_transform": latency_ms,
                    "saved_eff_est": (
                        ((baseline_tokens - image_tokens_est) / baseline_tokens)
                        if applied and baseline_tokens
                        else 0.0
                    ),
                },
            )
        except Exception:
            traceback.print_exc()

    return await forward_stream(client, request.method, upstream_url, headers, out_body)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "oxpipe"})
