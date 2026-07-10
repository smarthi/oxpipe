from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from oxpipe.config import Settings
from oxpipe.gate.estimate import should_image
from oxpipe.render.pages import render_text_to_pages
from oxpipe.render.profiles import RenderProfile, load_profile_map, resolve_profile
from oxpipe.transform.factsheet import extract_factsheet


@dataclass
class TransformResult:
    body: dict[str, Any]
    applied: bool
    reason: str
    pages: int = 0
    baseline_tokens: int = 0
    image_tokens_est: int = 0
    model: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _png_data_url(png: bytes) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _join_blobs(blobs: list[str]) -> str:
    return "\n\n-----\n\n".join(b for b in blobs if b)


def build_imaged_payload(
    text: str,
    profile: RenderProfile,
    settings: Settings,
) -> tuple[list[dict[str, Any]], TransformResult] | tuple[None, TransformResult]:
    """Render text; return content parts for Responses-style input_text/input_image."""
    pages = render_text_to_pages(text, profile)
    dims = [(p.width, p.height) for p in pages]
    decision = should_image(text, dims, profile, settings.min_chars)
    if not decision.image:
        return None, TransformResult(
            body={},
            applied=False,
            reason=decision.reason,
            pages=len(pages),
            baseline_tokens=decision.text_tokens,
            image_tokens_est=decision.image_tokens,
        )

    fs = extract_factsheet(text)
    parts: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "The following pages are oxpipe-rendered context images. "
                "Use them for gist; prefer the fact-sheet for exact ids/paths/ports."
            ),
        },
        {"type": "input_text", "text": fs.format()},
    ]
    for page in pages:
        parts.append(
            {
                "type": "input_image",
                "image_url": _png_data_url(page.png),
                "detail": profile.detail,
            }
        )
    return parts, TransformResult(
        body={},
        applied=True,
        reason="ok",
        pages=len(pages),
        baseline_tokens=decision.text_tokens,
        image_tokens_est=decision.image_tokens,
    )


def build_chat_image_parts(text: str, profile: RenderProfile, settings: Settings) -> tuple[list[dict[str, Any]], TransformResult] | tuple[None, TransformResult]:
    pages = render_text_to_pages(text, profile)
    dims = [(p.width, p.height) for p in pages]
    decision = should_image(text, dims, profile, settings.min_chars)
    if not decision.image:
        return None, TransformResult(
            body={},
            applied=False,
            reason=decision.reason,
            pages=len(pages),
            baseline_tokens=decision.text_tokens,
            image_tokens_est=decision.image_tokens,
        )
    fs = extract_factsheet(text)
    parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "The following pages are oxpipe-rendered context images. "
                "Use them for gist; prefer the fact-sheet for exact ids/paths/ports.\n\n"
                + fs.format()
            ),
        }
    ]
    for page in pages:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": _png_data_url(page.png), "detail": profile.detail},
            }
        )
    return parts, TransformResult(
        body={},
        applied=True,
        reason="ok",
        pages=len(pages),
        baseline_tokens=decision.text_tokens,
        image_tokens_est=decision.image_tokens,
    )


_PROFILES_CACHE: dict[int, dict[str, RenderProfile]] = {}


def profiles_for(settings: Settings) -> dict[str, RenderProfile]:
    key = id(settings)
    if key not in _PROFILES_CACHE:
        _PROFILES_CACHE[key] = load_profile_map(settings)
    return _PROFILES_CACHE[key]


def clear_profile_cache() -> None:
    _PROFILES_CACHE.clear()
