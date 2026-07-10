# oxpipe

OpenAI analogue of [pxpipe](https://github.com/teamchong/pxpipe) (Anthropic Fable/Opus).

Local proxy that renders bulky request context as compact PNGs to cut input tokens — with a text fact-sheet for exact identifiers. Built for **GPT-5.5 and GPT-5.6** over `/v1/responses` and `/v1/chat/completions`.

Design: [SPEC.md](./SPEC.md)

## Install

```bash
cd ~/projects/oxpipe
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional (better glyphs): `sudo apt install fonts-dejavu-core`

## Quick start

```bash
# 1) Start proxy (imaging off by default — safe passthrough)
export OXPIPE_MODELS=off
oxpipe serve

# 2) Open the live dashboard
#    http://127.0.0.1:47822/
#    (same UI at /dashboard)

# 3) Point OpenAI clients at the proxy
export OPENAI_BASE_URL=http://127.0.0.1:47822/v1
# keep using your normal OPENAI_API_KEY
```

## Dashboard

With `oxpipe serve` running, open:

**http://127.0.0.1:47822/**

What you can do there:

| Control | Effect |
|---|---|
| Compression kill switch | Off = every request passthrough (even if models are allowlisted) |
| Model chips (`gpt-5.5`, `gpt-5.6`, `gpt-5.6-sol`) | Runtime allowlist override (prefix match) |
| Counters / recent table | Live baseline vs actual tokens and `saved_eff` |

API equivalents:

```bash
curl -s http://127.0.0.1:47822/api/state | jq .
curl -s -X POST http://127.0.0.1:47822/api/compression \
  -H 'content-type: application/json' \
  -d '{"enabled": true}'
curl -s -X POST http://127.0.0.1:47822/api/models \
  -H 'content-type: application/json' \
  -d '{"models":["gpt-5.5","gpt-5.6"]}'
```

Env allowlist still works (and is the default until you toggle chips):

```bash
export OXPIPE_MODELS=gpt-5.5,gpt-5.6
oxpipe serve
```

## Counterfactual billing

Enabled by default (`OXPIPE_COUNTERFACTUAL=on`).

For allowlisted traffic oxpipe:

1. Probes OpenAI **`POST /v1/responses/input_tokens`** on the **original uncompressed** request (true text baseline)
2. Forwards the (possibly imaged) request upstream
3. Reads billed **`usage`** from the response body or SSE stream
4. Logs cache-honest savings to `~/.oxpipe/events.jsonl` and the dashboard

```text
actual_eff   = uncached + cached * cache_read_rate
baseline_eff = actual_eff + (baseline - actual_input) * (cache_read_rate if warm else 1)
saved_eff    = baseline_eff - actual_eff
```

The provider cache discount is applied to **both** sides, so it is never counted as an oxpipe win.

```bash
# default — live probe + usage parse
export OXPIPE_COUNTERFACTUAL=on
oxpipe serve

# offline / no probe — local token estimates only
export OXPIPE_COUNTERFACTUAL=off
oxpipe serve

# inspect measured rows
oxpipe stats
tail -n 5 ~/.oxpipe/events.jsonl
```

Chat Completions streams automatically get `stream_options.include_usage=true` so usage is present in SSE.

## CLI

```bash
oxpipe doctor   # config, fonts, upstream, dashboard URL
oxpipe stats    # summarize events.jsonl
oxpipe render --in notes.txt --out /tmp/oxpipe-pages --model gpt-5.6
```

## Behavior

- Non-allowlisted models → byte-identical passthrough
- Transform errors → fail open (original body forwarded)
- System / `instructions` are eligible even with a live tail; last N chat turns stay text
- Tool schemas stay JSON; large prior text may be imaged when the profitability gate wins
- Events: `~/.oxpipe/events.jsonl`

## Tests

```bash
pytest -q
pytest --cov=oxpipe --cov-report=term-missing -q
```
