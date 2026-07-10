from __future__ import annotations

import threading
from collections import deque
from typing import Any

from pydantic import BaseModel, Field


KNOWN_MODEL_CHIPS = ["gpt-5.5", "gpt-5.6", "gpt-5.6-sol"]


class RuntimeState:
    """Process-local dashboard controls (kill switch, model chips, recent events)."""

    def __init__(self, initial_models: list[str] | None = None) -> None:
        self._lock = threading.Lock()
        self.compression_enabled: bool = True
        # None => use settings.models from env; list => dashboard override
        self.models_override: list[str] | None = None
        self.initial_models: list[str] = list(initial_models or [])
        self.recent: deque[dict[str, Any]] = deque(maxlen=40)
        self.counters: dict[str, float] = {
            "requests": 0,
            "applied": 0,
            "baseline_tokens": 0,
            "actual_input_tokens": 0,
            "saved_eff": 0,
        }

    def effective_models(self, settings_models: list[str]) -> list[str]:
        with self._lock:
            if self.models_override is not None:
                return list(self.models_override)
            return list(settings_models)

    def model_allowed(self, model: str | None, settings_models: list[str]) -> bool:
        if not self.compression_enabled:
            return False
        if not model:
            return False
        models = self.effective_models(settings_models)
        if not models:
            return False
        m = model.lower()
        return any(m == p or m.startswith(p) for p in models)

    def set_compression(self, enabled: bool) -> None:
        with self._lock:
            self.compression_enabled = enabled

    def set_models(self, models: list[str]) -> None:
        with self._lock:
            cleaned = [m.strip().lower() for m in models if m.strip()]
            self.models_override = cleaned

    def record(self, event: dict[str, Any]) -> None:
        with self._lock:
            self.recent.appendleft(event)
            self.counters["requests"] += 1
            if event.get("applied"):
                self.counters["applied"] += 1
            self.counters["baseline_tokens"] += float(event.get("baseline_tokens") or 0)
            self.counters["actual_input_tokens"] += float(event.get("input_tokens") or 0)
            self.counters["saved_eff"] += float(event.get("saved_eff") or 0)

    def snapshot(self, settings_models: list[str]) -> dict[str, Any]:
        with self._lock:
            eff = (
                list(self.models_override)
                if self.models_override is not None
                else list(settings_models)
            )
            return {
                "compression_enabled": self.compression_enabled,
                "models": eff,
                "models_from_env": list(settings_models),
                "override_active": self.models_override is not None,
                "chips": KNOWN_MODEL_CHIPS,
                "recent": list(self.recent),
                "counters": dict(self.counters),
            }


class CompressionBody(BaseModel):
    enabled: bool


class ModelsBody(BaseModel):
    models: list[str] = Field(default_factory=list)
