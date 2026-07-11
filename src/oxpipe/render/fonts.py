from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


@lru_cache(maxsize=8)
def load_font(name: str, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load a monospace font; fall back to Pillow default."""
    candidates: list[Path] = []
    # Common Linux / WSL / macOS font locations
    for base in (
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path.home() / "Library" / "Fonts",
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
        Path("/opt/homebrew/share/fonts"),
        Path("/usr/local/share/fonts"),
    ):
        if not base.exists():
            continue
        for pattern in (
            "**/DejaVuSansMono.ttf",
            "**/DejaVuSansMono-Bold.ttf",
            "**/LiberationMono-Regular.ttf",
            "**/UbuntuMono-R.ttf",
            "**/NotoSansMono-Regular.ttf",
            "**/JetBrainsMono*.ttf",
            "**/Courier New.ttf",
            "**/CourierNew.ttf",
            "**/Menlo.ttc",
            "**/Monaco.ttf",
            "**/SFMono-Regular.otf",
            "**/cour.ttf",
        ):
            candidates.extend(base.glob(pattern))

    # Prefer name hint
    preferred = [c for c in candidates if name.lower().replace(" ", "") in c.stem.lower().replace(" ", "")]
    for path in preferred + candidates:
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def font_available() -> tuple[bool, str]:
    font = load_font("DejaVuSansMono", 12)
    if isinstance(font, ImageFont.FreeTypeFont):
        return True, getattr(font, "path", "truetype")
    return False, "PIL default (install DejaVu/JetBrains Mono — apt fonts-dejavu-core or brew font-dejavu)"
