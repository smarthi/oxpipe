from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UsageSnapshot(BaseModel):
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)


class SavingsResult(BaseModel):
    """Cache-honest OpenAI savings (provider cache discount applied to both sides)."""

    baseline_tokens: int
    actual_input_tokens: int
    cached_tokens: int
    image_tokens_est: int
    actual_eff: float
    baseline_eff: float
    saved_eff: float
    saved_frac: float
    cache_read_rate: float


def extract_usage(payload: dict[str, Any] | None) -> UsageSnapshot:
    if not payload:
        return UsageSnapshot()
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return UsageSnapshot()
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    cached = 0
    details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = int(details.get("cached_tokens") or 0)
    if not cached:
        cached = int(usage.get("cached_tokens") or 0)
    cached = min(cached, input_tokens) if input_tokens else cached
    return UsageSnapshot(
        input_tokens=input_tokens,
        cached_tokens=cached,
        output_tokens=output_tokens,
        raw=dict(usage),
    )


def compute_savings(
    *,
    baseline_tokens: int,
    usage: UsageSnapshot,
    image_tokens_est: int,
    cache_read_rate: float = 0.1,
) -> SavingsResult:
    """
    actual_eff   = uncached + cached * cache_read_rate
    baseline_eff = actual_eff + (baseline_tokens - actual_input) * rate

    When the real request was warm (cached>0), the text counterfactual delta is
    also priced at cache_read_rate; otherwise at 1.0. Never credits the
    provider cache discount itself as oxpipe savings.
    """
    actual_input = usage.input_tokens
    cached = min(usage.cached_tokens, actual_input) if actual_input else 0

    if not actual_input and image_tokens_est:
        # Response usage missing — fall back to image estimate as cold actual
        actual_input = image_tokens_est
        cached = 0

    uncached = max(0, actual_input - cached)
    actual_eff = float(uncached + cached * cache_read_rate)

    delta = max(0, int(baseline_tokens) - int(actual_input)) if baseline_tokens else 0
    rate = cache_read_rate if cached > 0 else 1.0
    baseline_eff = actual_eff + delta * rate
    saved_eff = baseline_eff - actual_eff
    saved_frac = (saved_eff / baseline_eff) if baseline_eff else 0.0
    return SavingsResult(
        baseline_tokens=int(baseline_tokens or 0),
        actual_input_tokens=int(actual_input),
        cached_tokens=int(cached),
        image_tokens_est=int(image_tokens_est or 0),
        actual_eff=actual_eff,
        baseline_eff=baseline_eff,
        saved_eff=saved_eff,
        saved_frac=saved_frac,
        cache_read_rate=cache_read_rate,
    )
