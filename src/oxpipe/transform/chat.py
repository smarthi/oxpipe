from __future__ import annotations

import copy
from typing import Any

from oxpipe.config import Settings
from oxpipe.render.profiles import resolve_profile
from oxpipe.transform.common import TransformResult, build_chat_image_parts, profiles_for
from oxpipe.transform.split import extract_chat_messages_text


def transform_chat(body: dict[str, Any], settings: Settings) -> TransformResult:
    model = body.get("model")
    if not settings.model_allowed(model if isinstance(model, str) else None):
        return TransformResult(body=body, applied=False, reason="model_not_allowlisted", model=model)

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return TransformResult(body=body, applied=False, reason="nothing_to_image", model=model)

    profiles = profiles_for(settings)
    profile = resolve_profile(model if isinstance(model, str) else None, profiles, settings.detail)

    blobs, idxs = extract_chat_messages_text(messages, settings.live_tail)
    if not blobs:
        return TransformResult(body=body, applied=False, reason="nothing_to_image", model=model)

    text = "\n\n-----\n\n".join(blobs)
    parts, meta = build_chat_image_parts(text, profile, settings)
    meta.model = model if isinstance(model, str) else None
    if parts is None:
        meta.body = body
        return meta

    out = copy.deepcopy(body)
    out_messages = out["messages"]
    assert isinstance(out_messages, list)

    for i in idxs:
        msg = out_messages[i]
        role = (msg.get("role") or "user").lower()
        if role == "tool":
            msg["content"] = "[oxpipe: tool result moved to imaged context]"
        else:
            msg["content"] = "[oxpipe: prior message moved to imaged context]"

    # Attach images on a synthetic user message near the front (after any remaining system stub)
    image_msg = {"role": "user", "content": parts}
    # Insert after leading system/developer messages that we didn't blank entirely
    insert_at = 0
    for i, msg in enumerate(out_messages):
        if (msg.get("role") or "").lower() in {"system", "developer"}:
            insert_at = i + 1
        else:
            break
    out_messages.insert(insert_at, image_msg)
    out["messages"] = out_messages

    meta.body = out
    meta.applied = True
    return meta
