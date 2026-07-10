from __future__ import annotations

from oxpipe.billing.counterfactual import (
    chat_body_to_count_payload,
    parse_usage_from_sse,
    responses_body_to_count_payload,
)
from oxpipe.billing.savings import UsageSnapshot, compute_savings, extract_usage


def test_extract_usage_responses_shape():
    u = extract_usage(
        {
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 50,
                "input_tokens_details": {"cached_tokens": 400},
            }
        }
    )
    assert u.input_tokens == 1000
    assert u.cached_tokens == 400
    assert u.output_tokens == 50


def test_extract_usage_chat_shape():
    u = extract_usage({"usage": {"prompt_tokens": 800, "completion_tokens": 20, "cached_tokens": 100}})
    assert u.input_tokens == 800
    assert u.cached_tokens == 100


def test_compute_savings_warm_cache():
    usage = UsageSnapshot(input_tokens=3000, cached_tokens=2000, output_tokens=10)
    s = compute_savings(baseline_tokens=10000, usage=usage, image_tokens_est=3000, cache_read_rate=0.1)
    # uncached=1000, cached=2000*0.1=200 → actual_eff=1200
    # delta=7000 * 0.1 = 700 → baseline_eff=1900, saved=700
    assert abs(s.actual_eff - 1200) < 1e-6
    assert abs(s.saved_eff - 700) < 1e-6
    assert s.saved_frac > 0


def test_compute_savings_cold():
    usage = UsageSnapshot(input_tokens=3000, cached_tokens=0, output_tokens=10)
    s = compute_savings(baseline_tokens=10000, usage=usage, image_tokens_est=3000, cache_read_rate=0.1)
    assert abs(s.actual_eff - 3000) < 1e-6
    assert abs(s.saved_eff - 7000) < 1e-6


def test_parse_sse_usage():
    sse = (
        'data: {"id":"1","choices":[{"delta":{"content":"hi"}}]}\n\n'
        'data: {"usage":{"prompt_tokens":120,"completion_tokens":5,"cached_tokens":0}}\n\n'
        "data: [DONE]\n\n"
    )
    u = parse_usage_from_sse(sse)
    assert u.input_tokens == 120
    assert u.output_tokens == 5


def test_chat_to_count_payload():
    body = {
        "model": "gpt-5.6",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ],
        "tools": [{"type": "function", "function": {"name": "x", "parameters": {}}}],
    }
    p = chat_body_to_count_payload(body)
    assert p["model"] == "gpt-5.6"
    assert p["instructions"] == "You are helpful."
    assert p["input"][0]["role"] == "user"
    assert p["tools"]


def test_responses_count_payload_strips_stream():
    body = {"model": "gpt-5.6", "input": "hi", "stream": True, "temperature": 0.2}
    p = responses_body_to_count_payload(body)
    assert "stream" not in p
    assert p["input"] == "hi"
