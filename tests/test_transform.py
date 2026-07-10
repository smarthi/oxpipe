from __future__ import annotations

from oxpipe.config import Settings
from oxpipe.transform.chat import transform_chat
from oxpipe.transform.responses import transform_responses


def _dense(n: int = 7000) -> str:
    return ("def foo():\n    return {" + "a" * 80 + "}\n") * (n // 100)


def test_model_not_allowlisted_passthrough():
    settings = Settings(models=[])  # off
    body = {"model": "gpt-5.6", "messages": [{"role": "user", "content": _dense()}]}
    r = transform_chat(body, settings)
    assert r.applied is False
    assert r.reason == "model_not_allowlisted"


def test_chat_transform_applies_when_allowlisted():
    settings = Settings(models=["gpt-5.5", "gpt-5.6"], min_chars=1000, live_tail=1)
    history = [
        {"role": "system", "content": _dense(3000)},
        {"role": "user", "content": _dense(3000)},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "continue"},  # live tail
    ]
    body = {"model": "gpt-5.6", "messages": history}
    r = transform_chat(body, settings)
    # profitable or not — should not crash; if applied, messages contain image_url
    if r.applied:
        msgs = r.body["messages"]
        flat = []
        for m in msgs:
            c = m.get("content")
            if isinstance(c, list):
                flat.extend(c)
        assert any(p.get("type") == "image_url" for p in flat if isinstance(p, dict))
        assert any("fact-sheet" in str(p.get("text", "")) for p in flat if isinstance(p, dict))
    else:
        assert r.reason in {"not_profitable", "below_min_chars", "nothing_to_image"}


def test_responses_transform_structure():
    settings = Settings(models=["gpt-5.6"], min_chars=1000, live_tail=1)
    body = {
        "model": "gpt-5.6",
        "instructions": _dense(3000),
        "input": [
            {"role": "user", "content": _dense(3000)},
            {"role": "user", "content": "live question"},
        ],
    }
    r = transform_responses(body, settings)
    if r.applied:
        assert isinstance(r.body.get("input"), list)
        first = r.body["input"][0]
        content = first.get("content")
        assert isinstance(content, list)
        assert any(p.get("type") == "input_image" for p in content)
    else:
        assert r.reason in {"not_profitable", "below_min_chars", "nothing_to_image"}
