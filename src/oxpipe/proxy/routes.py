from __future__ import annotations

import asyncio
import json
import time
import traceback
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from oxpipe.billing.counterfactual import (
    count_input_tokens,
    fallback_baseline_tokens,
)
from oxpipe.billing.savings import UsageSnapshot, compute_savings
from oxpipe.config import Settings
from oxpipe.events.log import append_event
from oxpipe.proxy.upstream import filter_request_headers, forward_stream, read_body
from oxpipe.runtime.state import RuntimeState
from oxpipe.transform.chat import transform_chat
from oxpipe.transform.responses import transform_responses


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if path in {"/", ""}:
        return "/v1"
    if path.startswith("/v1/") or path == "/v1":
        return path
    return "/v1" + path


def _ensure_chat_usage_stream(body: dict[str, Any]) -> dict[str, Any]:
    if not body.get("stream"):
        return body
    out = dict(body)
    opts = dict(out.get("stream_options") or {})
    opts["include_usage"] = True
    out["stream_options"] = opts
    return out


async def handle_openai_proxy(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    runtime: RuntimeState = request.app.state.runtime
    client = request.app.state.http
    path = _normalize_path(request.url.path)
    upstream_url = f"{settings.upstream}{path}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    raw = await read_body(request)
    headers = filter_request_headers(dict(request.headers))
    headers.setdefault("Accept", "application/json")

    applied = False
    reason = "passthrough"
    model: str | None = None
    pages = 0
    baseline_tokens = 0
    baseline_source = "none"
    image_tokens_est = 0
    t0 = time.perf_counter()
    out_body = raw
    original_body: dict[str, Any] | None = None
    should_log = False

    should_transform = request.method.upper() == "POST" and path in {
        "/v1/responses",
        "/v1/chat/completions",
    }

    if should_transform and raw:
        try:
            original_body = json.loads(raw)
            model = original_body.get("model") if isinstance(original_body.get("model"), str) else None
            eff_models = runtime.effective_models(settings.models)
            eff_settings = settings.model_copy(update={"models": eff_models})

            if not runtime.compression_enabled:
                reason = "compression_disabled"
            elif not eff_settings.model_allowed(model):
                reason = "model_not_allowlisted"
            else:
                should_log = True
                count_task = None
                if settings.counterfactual:
                    count_task = asyncio.create_task(
                        count_input_tokens(
                            client,
                            upstream=settings.upstream,
                            headers=headers,
                            path=path,
                            original_body=original_body,
                        )
                    )

                if path == "/v1/responses":
                    result = transform_responses(original_body, eff_settings)
                else:
                    result = transform_chat(original_body, eff_settings)

                applied = result.applied
                reason = result.reason
                pages = result.pages
                image_tokens_est = result.image_tokens_est

                if count_task is not None:
                    counted, creason = await count_task
                    if counted is not None:
                        baseline_tokens = counted
                        baseline_source = "input_tokens.count"
                    else:
                        baseline_tokens = fallback_baseline_tokens(original_body, path)
                        baseline_source = f"estimate:{creason}"
                else:
                    baseline_tokens = result.baseline_tokens or fallback_baseline_tokens(original_body, path)
                    baseline_source = "gate_estimate"

                if not baseline_tokens:
                    baseline_tokens = result.baseline_tokens

                if result.applied:
                    fwd = result.body
                    if path == "/v1/chat/completions":
                        fwd = _ensure_chat_usage_stream(fwd)
                    out_body = json.dumps(fwd).encode("utf-8")
                    headers["content-type"] = "application/json"
                elif path == "/v1/chat/completions" and original_body.get("stream"):
                    out_body = json.dumps(_ensure_chat_usage_stream(original_body)).encode("utf-8")
                    headers["content-type"] = "application/json"
        except Exception as exc:
            applied = False
            reason = f"transform_error:{type(exc).__name__}"
            out_body = raw
            should_log = True
            traceback.print_exc()

    latency_ms = int((time.perf_counter() - t0) * 1000)

    def _finalize(usage: UsageSnapshot) -> None:
        if not should_log and not applied:
            return
        try:
            savings = compute_savings(
                baseline_tokens=baseline_tokens,
                usage=usage,
                image_tokens_est=image_tokens_est,
                cache_read_rate=settings.cache_read_rate,
            )
            event = {
                "path": path,
                "model": model,
                "applied": applied,
                "reason": reason,
                "baseline_tokens": savings.baseline_tokens,
                "baseline_source": baseline_source,
                "image_tokens_est": image_tokens_est,
                "input_tokens": usage.input_tokens,
                "cached_tokens": usage.cached_tokens,
                "output_tokens": usage.output_tokens,
                "actual_eff": savings.actual_eff,
                "baseline_eff": savings.baseline_eff,
                "saved_eff": savings.saved_eff,
                "saved_frac": savings.saved_frac,
                "pages": pages,
                "latency_ms_transform": latency_ms,
            }
            append_event(settings.events_path, event)
            runtime.record(event)
        except Exception:
            traceback.print_exc()

    # Always attach usage callback for transform candidates; otherwise plain forward
    if should_transform and (should_log or applied):
        return await forward_stream(
            client,
            request.method,
            upstream_url,
            headers,
            out_body,
            on_usage=_finalize,
        )

    return await forward_stream(client, request.method, upstream_url, headers, out_body)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "oxpipe"})
