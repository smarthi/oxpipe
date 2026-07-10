from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 47822
    upstream: str = "https://api.openai.com"
    models: list[str] = Field(default_factory=list)  # empty / off => imaging disabled
    live_tail: int = 3
    detail: str = "high"
    events_path: Path = Field(default_factory=lambda: Path.home() / ".oxpipe" / "events.jsonl")
    min_chars: int = 6000
    profiles_path: Path | None = None
    profile_overrides: dict[str, Any] = Field(default_factory=dict)
    cache_read_rate: float = 0.1
    counterfactual: bool = True  # live POST /v1/responses/input_tokens probe

    @property
    def imaging_enabled(self) -> bool:
        return bool(self.models)

    def model_allowed(self, model: str | None) -> bool:
        if not model or not self.imaging_enabled:
            return False
        m = model.lower()
        for prefix in self.models:
            if m == prefix or m.startswith(prefix):
                return True
        return False


def _parse_models(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw or raw.lower() in {"off", "0", "false", "none"}:
        return []
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    models = _parse_models(_env("OXPIPE_MODELS", "off"))
    events = Path(_env("OXPIPE_EVENTS", str(Path.home() / ".oxpipe" / "events.jsonl"))).expanduser()
    profiles_env = os.environ.get("OXPIPE_PROFILES", "").strip()
    profiles_path: Path | None = None
    overrides: dict[str, Any] = {}
    if profiles_env:
        if profiles_env.startswith("{") or profiles_env.startswith("---"):
            import yaml

            overrides = yaml.safe_load(profiles_env) or {}
        else:
            profiles_path = Path(profiles_env).expanduser()

    return Settings(
        host=_env("OXPIPE_HOST", "127.0.0.1"),
        port=_env_int("OXPIPE_PORT", 47822),
        upstream=_env("OXPIPE_UPSTREAM", "https://api.openai.com").rstrip("/"),
        models=models,
        live_tail=max(0, _env_int("OXPIPE_LIVE_TAIL", 3)),
        detail=_env("OXPIPE_DETAIL", "high"),
        events_path=events,
        min_chars=max(0, _env_int("OXPIPE_MIN_CHARS", 6000)),
        profiles_path=profiles_path,
        profile_overrides=overrides if isinstance(overrides, dict) else {},
        counterfactual=_env_bool("OXPIPE_COUNTERFACTUAL", True),
    )


def default_profiles_path() -> Path:
    """Resolve bundled or repo configs/profiles.default.yaml."""
    candidates = [
        Path(__file__).resolve().parent / "profiles.default.yaml",
        Path(__file__).resolve().parents[2] / "configs" / "profiles.default.yaml",
        Path.cwd() / "configs" / "profiles.default.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[1]


def summarize_settings(s: Settings) -> str:
    return json.dumps(
        {
            "host": s.host,
            "port": s.port,
            "upstream": s.upstream,
            "models": s.models or ["off"],
            "live_tail": s.live_tail,
            "detail": s.detail,
            "min_chars": s.min_chars,
            "counterfactual": s.counterfactual,
            "events": str(s.events_path),
            "dashboard": f"http://{s.host}:{s.port}/",
        },
        indent=2,
    )
