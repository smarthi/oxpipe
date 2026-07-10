from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

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
            # let starlette/httpx handle body as already decoded or raw stream
            if lk == "content-encoding":
                continue
            continue
        out[k] = v
    return out


async def forward_stream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    content: bytes | None,
) -> Response:
    req = client.build_request(method, url, headers=headers, content=content)
    upstream = await client.send(req, stream=True)

    async def body_iter() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        body_iter(),
        status_code=upstream.status_code,
        headers=filter_response_headers(upstream.headers),
    )


async def read_body(request: Request) -> bytes:
    return await request.body()
