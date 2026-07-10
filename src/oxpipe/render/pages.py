from __future__ import annotations

import textwrap

from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict

from oxpipe.render.fonts import load_font
from oxpipe.render.profiles import RenderProfile

BANNER = "oxpipe context page — prefer fact-sheet for exact ids/paths"


class RenderedPage(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: int
    total: int
    png: bytes
    width: int
    height: int
    text: str


def _wrap_lines(text: str, columns: int) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw == "":
            lines.append("")
            continue
        wrapped = textwrap.wrap(
            raw,
            width=columns,
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [""])
    return lines


def render_text_to_pages(text: str, profile: RenderProfile) -> list[RenderedPage]:
    """Rasterize text into one or more PNG pages."""
    lines = _wrap_lines(text, profile.columns)
    rows_per_page = profile.usable_rows
    chunks: list[list[str]] = []
    for i in range(0, max(1, len(lines)), rows_per_page):
        chunks.append(lines[i : i + rows_per_page])
    if not chunks:
        chunks = [[""]]

    total = len(chunks)
    pages: list[RenderedPage] = []
    font = load_font(profile.font, max(8, profile.cell_h - 2))
    pad_x, pad_y = 8, 4

    for idx, chunk in enumerate(chunks, start=1):
        body_h = len(chunk) * profile.cell_h
        height = min(profile.max_height_px, pad_y * 2 + profile.header_rows * profile.cell_h + body_h)
        width = profile.page_width
        img = Image.new("RGB", (width, height), (250, 250, 248))
        draw = ImageDraw.Draw(img)
        header = f"[{idx}/{total}] {BANNER}"
        draw.text((pad_x, pad_y), header[: profile.columns], fill=(40, 40, 40), font=font)
        y = pad_y + profile.header_rows * profile.cell_h
        page_text_lines = [header]
        for line in chunk:
            draw.text((pad_x, y), line[: profile.columns], fill=(20, 20, 20), font=font)
            page_text_lines.append(line)
            y += profile.cell_h
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        pages.append(
            RenderedPage(
                index=idx,
                total=total,
                png=buf.getvalue(),
                width=width,
                height=height,
                text="\n".join(page_text_lines),
            )
        )
    return pages
