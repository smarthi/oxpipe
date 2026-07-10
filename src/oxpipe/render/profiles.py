from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

import yaml

from oxpipe.config import Settings, default_profiles_path


@dataclass(frozen=True)
class RenderProfile:
    cell_w: int = 6
    cell_h: int = 10
    columns: int = 120
    max_height_px: int = 1536
    strip_width_px: int = 768
    detail: str = "high"
    font: str = "DejaVuSansMono"
    patch_multiplier: float = 1.0

    @property
    def header_rows(self) -> int:
        return 2

    @property
    def usable_rows(self) -> int:
        rows = max(1, self.max_height_px // self.cell_h - self.header_rows)
        return rows

    @property
    def page_width(self) -> int:
        # Prefer strip_width; also fit columns * cell_w + padding
        content_w = self.columns * self.cell_w + 16
        return max(self.strip_width_px, content_w)


def _as_profile(data: dict[str, Any], base: RenderProfile | None = None) -> RenderProfile:
    base = base or RenderProfile()
    allowed = {f.name for f in fields(RenderProfile)}
    kwargs = {k: v for k, v in data.items() if k in allowed}
    return replace(base, **kwargs)


def load_profile_map(settings: Settings) -> dict[str, RenderProfile]:
    path = settings.profiles_path or default_profiles_path()
    raw: dict[str, Any] = {}
    if path.is_file():
        with path.open() as f:
            loaded = yaml.safe_load(f) or {}
        if isinstance(loaded, dict):
            raw.update(loaded)
    for k, v in settings.profile_overrides.items():
        if isinstance(v, dict):
            raw[k] = {**(raw.get(k) or {}), **v}
    out: dict[str, RenderProfile] = {}
    for key, val in raw.items():
        if isinstance(val, dict):
            out[str(key).lower()] = _as_profile(val)
    if "gpt-5.5" not in out:
        out["gpt-5.5"] = RenderProfile()
    if "gpt-5.6" not in out:
        out["gpt-5.6"] = RenderProfile()
    return out


def resolve_profile(model: str | None, profiles: dict[str, RenderProfile], default_detail: str) -> RenderProfile:
    if not model:
        p = profiles.get("gpt-5.6", RenderProfile())
        return replace(p, detail=default_detail or p.detail)
    m = model.lower()
    # longest prefix match
    best: str | None = None
    for key in profiles:
        if m == key or m.startswith(key):
            if best is None or len(key) > len(best):
                best = key
    p = profiles[best] if best else profiles.get("gpt-5.6", RenderProfile())
    detail = default_detail or p.detail
    return replace(p, detail=detail)
