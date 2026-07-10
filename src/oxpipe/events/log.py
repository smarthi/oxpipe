from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_lock = threading.Lock()


def append_event(path: Path, event: dict[str, Any]) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if "ts" not in event:
        event = {**event, "ts": datetime.now(timezone.utc).isoformat()}
    line = json.dumps(event, ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_events(path: Path) -> list[dict[str, Any]]:
    path = path.expanduser()
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def summarize_events(path: Path) -> dict[str, Any]:
    rows = read_events(path)
    applied = [r for r in rows if r.get("applied")]
    gated = [r for r in rows if r.get("reason") == "not_profitable"]
    baseline = sum(float(r.get("baseline_tokens") or 0) for r in applied)
    actual = sum(float(r.get("input_tokens") or 0) for r in applied)
    image_est = sum(float(r.get("image_tokens_est") or 0) for r in applied)
    saved_eff = sum(float(r.get("saved_eff") or 0) for r in applied)
    baseline_eff = sum(float(r.get("baseline_eff") or 0) for r in applied)
    return {
        "events": len(rows),
        "applied": len(applied),
        "not_profitable": len(gated),
        "baseline_tokens_sum": baseline,
        "input_tokens_sum": actual,
        "image_tokens_est_sum": image_est,
        "saved_eff_sum": saved_eff,
        "baseline_eff_sum": baseline_eff,
        "saved_frac": (saved_eff / baseline_eff) if baseline_eff else 0.0,
        # legacy aliases
        "saved_tokens_est_sum": saved_eff,
        "saved_frac_est": (saved_eff / baseline_eff) if baseline_eff else 0.0,
    }
