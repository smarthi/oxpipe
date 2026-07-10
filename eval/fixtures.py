"""Offline eval fixtures for GPT-5.5 / GPT-5.6 imaged-context quality.

Run paid model checks separately once API access is available.
This package only prepares deterministic fixtures + local render pages.
"""

from __future__ import annotations

from pathlib import Path

FIXTURE = """# oxpipe recall fixture alpha
hex: c7a1e90b4d2f
field: retryBudgetSeconds
path: /srv/sol-pilot/releases/alpha-07/config/runtime-map.json
port: 47831
gist: rollout chose option B after canary failed
#region NOT STATED: region_code
"""


def write_fixture(dir: Path) -> Path:
    dir.mkdir(parents=True, exist_ok=True)
    path = dir / "alpha.txt"
    path.write_text(FIXTURE, encoding="utf-8")
    return path
