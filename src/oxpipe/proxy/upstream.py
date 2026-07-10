from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from oxpipe.billing.counterfactual import parse_usage_from_response_body, parse_usage_from_sse
from oxpipe.billing.savings import UsageSnapshot

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def filter_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP:
            continue
        out[k] = v
    return out


def filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP or lk == "content-encoding":
            continue
        out[k] = v
    return out


async def forward_stream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    content: bytes | None,
    *,
    on_usage: Callable[[UsageSnapshot], Any] | None = None,
) -> Response:
    req = client.build_request(method, url, headers=headers, content=content)
    upstream = await client.send(req, stream=True)
    content_type = upstream.headers.get("content-type", "")
    buf = bytearray()

    async def body_iter() -> AsyncIterator[bytes]:
        try:
            try:
                async for chunk in upstream.aiter_bytes():
                    if on_usage is not None:
                        buf.extend(chunk)
                    yield chunk
            except httpx.StreamConsumed:
                data = upstream.content
                if on_usage is not None:
                    buf.extend(data)
                yield data
        finally:
            if on_usage is not None:
                try:
                    usage = parse_usage_from_response_body(bytes(buf), content_type)
                    if usage.input_tokens == 0 and b"data:" in buf:
                        usage = parse_usage_from_sse(bytes(buf).decode("utf-8", errors="replace"))
                    on_usage(usage)
                except Exception:
                    on_usage(UsageSnapshot())
            await upstream.aclose()

    return StreamingResponse(
        body_iter(),
        status_code=upstream.status_code,
        headers=filter_response_headers(upstream.headers),
    )


async def read_body(request: Request) -> bytes:
    return await request.body()
