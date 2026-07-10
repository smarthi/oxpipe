from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from oxpipe.billing.counterfactual import (
    chat_body_to_count_payload,
    count_input_tokens,
    fallback_baseline_tokens,
    parse_usage_from_response_body,
    parse_usage_from_sse,
)
from oxpipe.billing.savings import UsageSnapshot, compute_savings, extract_usage
from oxpipe.config import Settings, load_settings, summarize_settings
from oxpipe.events.log import append_event, read_events, summarize_events
from oxpipe.gate.estimate import detect_chars_per_token, estimate_image_tokens, should_image
from oxpipe.proxy.routes import _ensure_chat_usage_stream, _normalize_path
from oxpipe.render.fonts import font_available
from oxpipe.render.profiles import RenderProfile, load_profile_map, resolve_profile
from oxpipe.runtime.state import RuntimeState
from oxpipe.transform.factsheet import looks_secretish
from oxpipe.transform.split import extract_chat_messages_text, extract_responses_input_text


def test_normalize_path_variants():
    assert _normalize_path("chat/completions") == "/v1/chat/completions"
    assert _normalize_path("/chat/completions") == "/v1/chat/completions"
    assert _normalize_path("/v1/responses") == "/v1/responses"
    assert _normalize_path("/") == "/v1"


def test_ensure_chat_usage_stream():
    assert _ensure_chat_usage_stream({"model": "x"}) == {"model": "x"}
    out = _ensure_chat_usage_stream({"stream": True})
    assert out["stream_options"]["include_usage"] is True


def test_runtime_kill_switch_and_models():
    rt = RuntimeState(initial_models=["gpt-5.6"])
    assert rt.model_allowed("gpt-5.6", ["gpt-5.6"])
    rt.set_compression(False)
    assert not rt.model_allowed("gpt-5.6", ["gpt-5.6"])
    rt.set_compression(True)
    rt.set_models(["gpt-5.5"])
    assert rt.model_allowed("gpt-5.5-preview", ["gpt-5.6"])
    assert not rt.model_allowed("gpt-5.6", ["gpt-5.6"])
    assert not rt.model_allowed(None, ["gpt-5.5"])
    rt.record({"applied": True, "baseline_tokens": 100, "input_tokens": 40, "saved_eff": 60})
    snap = rt.snapshot(["gpt-5.6"])
    assert snap["override_active"] is True
    assert snap["counters"]["applied"] == 1
    assert snap["counters"]["saved_eff"] == 60


def test_events_roundtrip(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    append_event(path, {"applied": True, "baseline_tokens": 100, "input_tokens": 40, "saved_eff": 55, "baseline_eff": 95})
    append_event(path, {"applied": False, "reason": "not_profitable"})
    rows = read_events(path)
    assert len(rows) == 2
    assert "ts" in rows[0]
    summary = summarize_events(path)
    assert summary["events"] == 2
    assert summary["applied"] == 1
    assert summary["not_profitable"] == 1
    assert summary["saved_eff_sum"] == 55


def test_load_settings_models_off(monkeypatch):
    monkeypatch.setenv("OXPIPE_MODELS", "off")
    monkeypatch.setenv("OXPIPE_COUNTERFACTUAL", "false")
    s = load_settings()
    assert s.models == []
    assert s.counterfactual is False
    assert "dashboard" in summarize_settings(s)


def test_load_settings_models_list(monkeypatch):
    monkeypatch.setenv("OXPIPE_MODELS", "gpt-5.5, gpt-5.6")
    s = load_settings()
    assert s.models == ["gpt-5.5", "gpt-5.6"]
    assert s.model_allowed("gpt-5.6-sol")
    assert not s.model_allowed("gpt-4o")


def test_split_keeps_system_out_of_live_tail():
    messages = [
        {"role": "system", "content": "SYS " * 100},
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "live"},
    ]
    blobs, idxs = extract_chat_messages_text(messages, live_tail=2)
    assert 0 in idxs  # system always eligible
    assert 1 in idxs  # older user turn eligible
    assert 2 not in idxs and 3 not in idxs  # live tail protected
    assert any("SYS" in b for b in blobs)


def test_split_responses_instructions_always():
    body = {
        "instructions": "INST " * 50,
        "input": [
            {"role": "user", "content": "old"},
            {"role": "user", "content": "live"},
        ],
    }
    blobs, locs = extract_responses_input_text(body, live_tail=1)
    assert ("instructions", -1) in locs
    assert any("INST" in b for b in blobs)


def test_gate_detail_low_and_density():
    assert detect_chars_per_token('{"a":1}') < 4
    assert detect_chars_per_token("hello world plain prose here") >= 2
    p = RenderProfile(detail="low")
    assert estimate_image_tokens(1024, 1024, p) >= 1
    d = should_image("tiny", [(100, 100)], RenderProfile(), min_chars=6000)
    assert d.reason == "below_min_chars"


def test_factsheet_secretish():
    assert looks_secretish("key=sk-abc1234567890xyz")


def test_parse_usage_json_and_sse_responses():
    u = parse_usage_from_response_body(
        json.dumps({"usage": {"input_tokens": 9, "output_tokens": 1}}).encode(),
        "application/json",
    )
    assert u.input_tokens == 9
    sse = 'data: {"type":"response.completed","response":{"usage":{"input_tokens":77,"output_tokens":3}}}\n\n'
    u2 = parse_usage_from_sse(sse)
    assert u2.input_tokens == 77


def test_fallback_baseline():
    n = fallback_baseline_tokens(
        {"model": "gpt-5.6", "messages": [{"role": "user", "content": "hello " * 100}]},
        "/v1/chat/completions",
    )
    assert n > 0


def test_chat_multimodal_count_payload():
    body = {
        "model": "gpt-5.6",
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "sys"}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "see"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx", "detail": "high"}},
                ],
            },
        ],
    }
    p = chat_body_to_count_payload(body)
    assert p["instructions"] == "sys"
    assert any(isinstance(c, list) for c in [p["input"][0]["content"]])


@pytest.mark.asyncio
async def test_count_input_tokens_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/responses/input_tokens")
        return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 4242})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        tokens, reason = await count_input_tokens(
            client,
            upstream="https://api.openai.com",
            headers={"Authorization": "Bearer x"},
            path="/v1/responses",
            original_body={"model": "gpt-5.6", "input": "hi"},
        )
    assert tokens == 4242
    assert reason == "ok"


@pytest.mark.asyncio
async def test_count_input_tokens_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "nope"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        tokens, reason = await count_input_tokens(
            client,
            upstream="https://api.openai.com",
            headers={"Authorization": "Bearer x"},
            path="/v1/chat/completions",
            original_body={"model": "gpt-5.6", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert tokens is None
    assert "401" in reason


def test_compute_savings_missing_usage_falls_back_to_image_est():
    s = compute_savings(
        baseline_tokens=5000,
        usage=UsageSnapshot(),
        image_tokens_est=1000,
        cache_read_rate=0.1,
    )
    assert s.actual_input_tokens == 1000
    assert s.saved_eff == 4000


def test_extract_usage_empty():
    assert extract_usage(None).input_tokens == 0
    assert extract_usage({}).input_tokens == 0


def test_profiles_and_font():
    s = Settings()
    profiles = load_profile_map(s)
    assert "gpt-5.5" in profiles and "gpt-5.6" in profiles
    p = resolve_profile("gpt-5.6-sol", profiles, "high")
    assert p.detail == "high"
    ok, msg = font_available()
    assert isinstance(ok, bool)
    assert msg
