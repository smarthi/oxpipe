from __future__ import annotations

import math

from pydantic import BaseModel

from oxpipe.render.profiles import RenderProfile


def estimate_text_tokens(text: str, chars_per_token: float | None = None) -> int:
    if not text:
        return 0
    if chars_per_token is None:
        chars_per_token = detect_chars_per_token(text)
    return max(1, math.ceil(len(text) / max(0.5, chars_per_token)))


def detect_chars_per_token(text: str) -> float:
    """Dense code/JSON ~1–1.5 chars/token; prose ~4."""
    sample = text[:4000]
    if not sample:
        return 4.0
    symbols = sum(1 for c in sample if c in "{}[]<>;=()/\\'\"`")
    density = symbols / len(sample)
    if density > 0.08:
        return 1.2
    if density > 0.04:
        return 2.0
    return 4.0


def estimate_image_tokens(width: int, height: int, profile: RenderProfile) -> int:
    """
    GPT-5.x style patch estimate: ceil(w/32)*ceil(h/32)*multiplier.
    For detail=high we also apply a soft short-side normalize toward 768
    similar to classic vision resizing (conservative upper bound if original).
    """
    w, h = width, height
    detail = (profile.detail or "high").lower()
    if detail == "low":
        return max(1, int(85 * profile.patch_multiplier))
    if detail in {"high", "auto"}:
        short, _long = (w, h) if w <= h else (h, w)
        if short > 768:
            scale = 768 / short
            w = max(1, int(w * scale))
            h = max(1, int(h * scale))
    patches = math.ceil(w / 32) * math.ceil(h / 32)
    return max(1, int(math.ceil(patches * profile.patch_multiplier)))


def estimate_pages_tokens(pages: list[tuple[int, int]], profile: RenderProfile) -> int:
    return sum(estimate_image_tokens(w, h, profile) for w, h in pages)


class GateDecision(BaseModel):
    image: bool
    reason: str
    text_tokens: int
    image_tokens: int


def should_image(text: str, page_dims: list[tuple[int, int]], profile: RenderProfile, min_chars: int) -> GateDecision:
    if len(text) < min_chars:
        return GateDecision(
            image=False,
            reason="below_min_chars",
            text_tokens=estimate_text_tokens(text),
            image_tokens=0,
        )
    text_tokens = estimate_text_tokens(text)
    image_tokens = estimate_pages_tokens(page_dims, profile)
    if image_tokens < text_tokens:
        return GateDecision(image=True, reason="ok", text_tokens=text_tokens, image_tokens=image_tokens)
    return GateDecision(
        image=False,
        reason="not_profitable",
        text_tokens=text_tokens,
        image_tokens=image_tokens,
    )
