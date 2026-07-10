from __future__ import annotations

import copy
from typing import Any

from oxpipe.config import Settings
from oxpipe.transform.common import TransformResult, build_imaged_payload, profiles_for
from oxpipe.render.profiles import resolve_profile
from oxpipe.transform.split import extract_responses_input_text


def transform_responses(body: dict[str, Any], settings: Settings) -> TransformResult:
    """Rewrite a Responses API request body. Fail-open: caller keeps original on error."""
    model = body.get("model")
    if not settings.model_allowed(model if isinstance(model, str) else None):
        return TransformResult(body=body, applied=False, reason="model_not_allowlisted", model=model)

    profiles = profiles_for(settings)
    profile = resolve_profile(model if isinstance(model, str) else None, profiles, settings.detail)

    blobs, locs = extract_responses_input_text(body, settings.live_tail)
    if not blobs:
        return TransformResult(body=body, applied=False, reason="nothing_to_image", model=model)

    text = "\n\n-----\n\n".join(blobs)
    parts, meta = build_imaged_payload(text, profile, settings)
    meta.model = model if isinstance(model, str) else None
    if parts is None:
        meta.body = body
        return meta

    out = copy.deepcopy(body)
    # Clear imaged sources: blank instructions / replace old input items with placeholder
    for kind, idx in locs:
        if kind == "instructions" and isinstance(out.get("instructions"), str):
            out["instructions"] = "[oxpipe: system/instructions moved to imaged context]"
        elif kind == "input":
            inp = out.get("input")
            if isinstance(inp, str):
                out["input"] = []
            elif isinstance(inp, list) and 0 <= idx < len(inp):
                item = inp[idx]
                if isinstance(item, dict):
                    role = item.get("role") or "user"
                    inp[idx] = {
                        "role": role,
                        "content": [
                            {
                                "type": "input_text",
                                "text": "[oxpipe: prior turn content moved to imaged context]",
                            }
                        ],
                    }
                elif isinstance(item, str):
                    inp[idx] = "[oxpipe: prior content moved to imaged context]"

    # Prepend a user message with images + fact-sheet
    image_msg = {"role": "user", "content": parts}
    inp = out.get("input")
    if isinstance(inp, list):
        out["input"] = [image_msg, *inp]
    elif isinstance(inp, str):
        out["input"] = [
            image_msg,
            {"role": "user", "content": [{"type": "input_text", "text": inp}]},
        ]
    else:
        out["input"] = [image_msg]

    meta.body = out
    meta.applied = True
    return meta
