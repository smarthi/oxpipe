from __future__ import annotations

import json
from typing import Any

import httpx

from oxpipe.billing.savings import UsageSnapshot, extract_usage
from oxpipe.gate.estimate import estimate_text_tokens


def chat_body_to_count_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Map Chat Completions body to Responses input_tokens count shape."""
    model = body.get("model")
    messages = body.get("messages") or []
    instructions_parts: list[str] = []
    input_items: list[Any] = []
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = (msg.get("role") or "user").lower()
            content = msg.get("content")
            if role in {"system", "developer"}:
                if isinstance(content, str):
                    instructions_parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            instructions_parts.append(str(block.get("text") or ""))
                        elif isinstance(block, str):
                            instructions_parts.append(block)
                continue
            # user/assistant/tool → input message
            if isinstance(content, str):
                input_items.append({"role": role if role in {"user", "assistant"} else "user", "content": content})
            elif isinstance(content, list):
                parts: list[dict[str, Any]] = []
                for block in content:
                    if isinstance(block, str):
                        parts.append({"type": "input_text", "text": block})
                    elif isinstance(block, dict):
                        btype = block.get("type")
                        if btype == "text":
                            parts.append({"type": "input_text", "text": str(block.get("text") or "")})
                        elif btype == "image_url":
                            url = block.get("image_url")
                            if isinstance(url, dict):
                                url = url.get("url")
                            parts.append(
                                {
                                    "type": "input_image",
                                    "image_url": url,
                                    "detail": (block.get("image_url") or {}).get("detail")
                                    if isinstance(block.get("image_url"), dict)
                                    else "high",
                                }
                            )
                input_items.append(
                    {"role": role if role in {"user", "assistant"} else "user", "content": parts or ""}
                )
            elif content is None and role == "assistant" and msg.get("tool_calls"):
                input_items.append({"role": "assistant", "content": json.dumps(msg.get("tool_calls"))})
    payload: dict[str, Any] = {"model": model, "input": input_items}
    if instructions_parts:
        payload["instructions"] = "\n\n".join(instructions_parts)
    # tools schemas also consume tokens
    if body.get("tools"):
        payload["tools"] = body["tools"]
    return payload


def responses_body_to_count_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Strip generation-only fields; keep count-relevant Responses fields."""
    keep = (
        "model",
        "input",
        "instructions",
        "tools",
        "tool_choice",
        "previous_response_id",
        "reasoning",
        "text",
        "truncation",
    )
    return {k: body[k] for k in keep if k in body}


async def count_input_tokens(
    client: httpx.AsyncClient,
    *,
    upstream: str,
    headers: dict[str, str],
    path: str,
    original_body: dict[str, Any],
    timeout: float = 30.0,
) -> tuple[int | None, str]:
    """
    Probe OpenAI POST /v1/responses/input_tokens on the uncompressed body.
    Returns (tokens, reason). tokens is None on failure.
    """
    if path == "/v1/chat/completions":
        payload = chat_body_to_count_payload(original_body)
    elif path == "/v1/responses":
        payload = responses_body_to_count_payload(original_body)
    else:
        return None, "unsupported_path"

    if not payload.get("model"):
        return None, "missing_model"

    url = f"{upstream.rstrip('/')}/v1/responses/input_tokens"
    req_headers = {k: v for k, v in headers.items() if k.lower() != "content-length"}
    req_headers["content-type"] = "application/json"
    try:
        resp = await client.post(url, headers=req_headers, json=payload, timeout=timeout)
        if resp.status_code >= 400:
            return None, f"count_http_{resp.status_code}"
        data = resp.json()
        tokens = data.get("input_tokens")
        if tokens is None:
            return None, "count_missing_field"
        return int(tokens), "ok"
    except Exception as exc:
        return None, f"count_error:{type(exc).__name__}"


def fallback_baseline_tokens(original_body: dict[str, Any], path: str) -> int:
    """Local estimate when the live count probe fails."""
    if path == "/v1/chat/completions":
        messages = original_body.get("messages") or []
        text_parts: list[str] = []
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    c = msg.get("content")
                    if isinstance(c, str):
                        text_parts.append(c)
                    elif isinstance(c, list):
                        for b in c:
                            if isinstance(b, dict) and "text" in b:
                                text_parts.append(str(b["text"]))
        return estimate_text_tokens("\n".join(text_parts))
    # responses
    parts: list[str] = []
    if isinstance(original_body.get("instructions"), str):
        parts.append(original_body["instructions"])
    inp = original_body.get("input")
    if isinstance(inp, str):
        parts.append(inp)
    elif isinstance(inp, list):
        parts.append(json.dumps(inp)[:200_000])
    return estimate_text_tokens("\n".join(parts))


def parse_usage_from_response_body(body: bytes, content_type: str | None) -> UsageSnapshot:
    ct = (content_type or "").lower()
    text = body.decode("utf-8", errors="replace")
    if "text/event-stream" in ct or text.lstrip().startswith("data:"):
        return parse_usage_from_sse(text)
    try:
        return extract_usage(json.loads(text))
    except json.JSONDecodeError:
        return UsageSnapshot()


def parse_usage_from_sse(text: str) -> UsageSnapshot:
    """Scan SSE for usage-bearing events (Responses + Chat Completions)."""
    last = UsageSnapshot()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        # Chat Completions: chunk with usage
        if "usage" in obj and isinstance(obj["usage"], dict):
            last = extract_usage(obj)
            continue
        # Responses: response.completed / response.done style
        resp = obj.get("response")
        if isinstance(resp, dict) and isinstance(resp.get("usage"), dict):
            last = extract_usage(resp)
            continue
        if obj.get("type") in {"response.completed", "response.done"} and isinstance(obj.get("response"), dict):
            last = extract_usage(obj["response"])
    return last
