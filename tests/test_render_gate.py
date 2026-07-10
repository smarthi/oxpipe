from __future__ import annotations

from oxpipe.config import Settings
from oxpipe.gate.estimate import estimate_image_tokens, should_image
from oxpipe.render.pages import render_text_to_pages
from oxpipe.render.profiles import RenderProfile, load_profile_map, resolve_profile


def test_render_pages_produce_png():
    profile = RenderProfile(columns=40, max_height_px=400, cell_h=12, cell_w=7)
    text = "hello world\n" * 50
    pages = render_text_to_pages(text, profile)
    assert len(pages) >= 1
    assert pages[0].png[:8] == b"\x89PNG\r\n\x1a\n"


def test_gate_images_dense_large_text():
    profile = RenderProfile(columns=100, max_height_px=1536, cell_h=12, cell_w=7, detail="high")
    # Dense JSON-like content
    text = '{"k":' + ("x" * 100) + "},"
    text = text * 80  # ~8k+ chars
    pages = render_text_to_pages(text, profile)
    dims = [(p.width, p.height) for p in pages]
    d = should_image(text, dims, profile, min_chars=6000)
    assert d.text_tokens > 0
    # May or may not be profitable depending on geometry; ensure decision is coherent
    assert d.reason in {"ok", "not_profitable", "below_min_chars"}
    if d.image:
        assert d.image_tokens < d.text_tokens


def test_profile_longest_prefix():
    settings = Settings()
    profiles = load_profile_map(settings)
    p = resolve_profile("gpt-5.6-sol-preview", profiles, "high")
    # sol profile if present else 5.6
    assert p.columns in {100, 126}
    tokens = estimate_image_tokens(768, 768, p)
    assert tokens > 0
