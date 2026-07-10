from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SplitResult(BaseModel):
    """Text blocks eligible for imaging vs kept as live text."""

    to_image: list[str] = Field(default_factory=list)
    total_imaged_chars: int = 0


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("type")
                if t in {"text", "input_text", "output_text"}:
                    parts.append(str(block.get("text") or ""))
                elif "text" in block and isinstance(block["text"], str):
                    parts.append(block["text"])
        return "\n".join(p for p in parts if p)
    return str(content)


def extract_chat_messages_text(messages: list[dict[str, Any]], live_tail: int) -> tuple[list[str], list[int]]:
    """
    Return (texts_to_image, indexes_imaged).

    System/developer messages are always eligible (static slab).
    Live-tail only protects the last N conversational turns (user/assistant/tool).
    """
    if not messages:
        return [], []

    # Indices of conversational messages (everything except system/developer)
    convo_idxs = [
        i
        for i, msg in enumerate(messages)
        if (msg.get("role") or "").lower() not in {"system", "developer"}
    ]
    protected = set(convo_idxs[len(convo_idxs) - live_tail :]) if live_tail > 0 else set()

    blobs: list[str] = []
    idxs: list[int] = []
    for i, msg in enumerate(messages):
        role = (msg.get("role") or "").lower()
        if role in {"system", "developer"}:
            text = _content_to_text(msg.get("content"))
            if text:
                blobs.append(text)
                idxs.append(i)
            continue
        if i in protected:
            continue
        if role in {"tool", "function", "user", "assistant"}:
            text = _content_to_text(msg.get("content"))
            if text:
                blobs.append(text)
                idxs.append(i)
    return blobs, idxs


def extract_responses_input_text(body: dict[str, Any], live_tail: int) -> tuple[list[str], list[tuple[str, int]]]:
    """
    Extract bulky text from Responses `input` / `instructions`.
    `instructions` always eligible. Live-tail applies to input message items only.
    """
    blobs: list[str] = []
    locs: list[tuple[str, int]] = []

    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        blobs.append(instructions)
        locs.append(("instructions", -1))

    inp = body.get("input")
    if isinstance(inp, str):
        items: list[Any] = [{"role": "user", "content": inp}]
        str_input = True
    elif isinstance(inp, list):
        items = inp
        str_input = False
    else:
        return blobs, locs

    convo_idxs = []
    for i, item in enumerate(items):
        if isinstance(item, str):
            convo_idxs.append(i)
            continue
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").lower()
        itype = (item.get("type") or "").lower()
        if role in {"system", "developer"}:
            continue
        if role or itype in {"message", "function_call_output", ""}:
            convo_idxs.append(i)

    protected = set(convo_idxs[len(convo_idxs) - live_tail :]) if live_tail > 0 else set()

    for i, item in enumerate(items):
        if isinstance(item, str):
            if i not in protected:
                blobs.append(item)
                locs.append(("input", i))
            continue
        if not isinstance(item, dict):
            continue
        itype = (item.get("type") or "").lower()
        if itype in {"function_call"}:
            continue
        if itype == "function_call_output":
            if i in protected:
                continue
            out = item.get("output")
            text = out if isinstance(out, str) else _content_to_text(out)
            if text:
                blobs.append(text)
                locs.append(("input", i))
            continue
        role = (item.get("role") or "").lower()
        if role in {"system", "developer"}:
            text = _content_to_text(item.get("content"))
            if text:
                blobs.append(text)
                locs.append(("input", i))
            continue
        if i in protected:
            continue
        if role in {"user", "assistant"} or itype in {"message", ""}:
            text = _content_to_text(item.get("content"))
            if text:
                blobs.append(text)
                locs.append(("input", i))
    _ = str_input
    return blobs, locs
