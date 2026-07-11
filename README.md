# oxpipe

OpenAI analogue of [pxpipe](https://github.com/teamchong/pxpipe) (Anthropic Fable/Opus).

Local proxy that renders bulky request context as compact PNGs to cut input tokens — with a text fact-sheet for exact identifiers. Built for **GPT-5.5 and GPT-5.6** over `/v1/responses` and `/v1/chat/completions`.

Design: [SPEC.md](./SPEC.md)

## Install

### Linux / WSL

```bash
cd ~/projects/oxpipe
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional (better glyphs): `sudo apt install fonts-dejavu-core`

### macOS

Requires **Python 3.11+** (Homebrew recommended):

```bash
# once
brew install python@3.12
# optional monospace font for clearer PNG pages
brew install --cask font-dejavu font-jetbrains-mono

cd ~/projects/oxpipe   # or wherever you cloned the repo
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
oxpipe doctor          # should report a real TTF path under Fonts, not "PIL default"
```

Apple Silicon and Intel Macs both work. Keep the terminal session with `.venv` activated when you `oxpipe serve`.

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

## Use with Codex Desktop

Codex Desktop does **not** reliably pick up a shell `OPENAI_BASE_URL`. Configure the proxy in **user-level** `~/.codex/config.toml` (project-local `.codex/config.toml` ignores provider/base URL keys).

### 1. Start oxpipe

```bash
cd ~/projects/oxpipe
source .venv/bin/activate
export OXPIPE_MODELS=gpt-5.5,gpt-5.6
oxpipe serve
```

Dashboard: http://127.0.0.1:47822/

### 2. Point Codex at oxpipe

Edit `~/.codex/config.toml`:

```toml
# use a GPT-5.5 / GPT-5.6 model id you actually have
model = "gpt-5.6"

# preferred: override the built-in OpenAI provider
openai_base_url = "http://127.0.0.1:47822/v1"
```

Alternative — custom provider:

```toml
model = "gpt-5.6"
model_provider = "oxpipe"

[model_providers.oxpipe]
name = "oxpipe"
base_url = "http://127.0.0.1:47822/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
```

### 3. Restart Codex Desktop

Quit and reopen the app so it reloads `config.toml`.

### 4. Confirm traffic

Open a coding session, then check:

- Dashboard recent rows for `/v1/responses`
- `tail -n 5 ~/.oxpipe/events.jsonl`

### Notes

- Auth stays your normal Codex / ChatGPT login or `OPENAI_API_KEY`; oxpipe only changes the base URL and forwards `Authorization`.
- Codex uses the **Responses** API (`/v1/responses`), which oxpipe supports.
- Warm, nearly fully cached prompts can show a low Saved % even when oxpipe is working; savings show up more when large uncached slabs or history collapse are imaged.
- Bail out: dashboard kill switch, or comment out `openai_base_url` and restart Codex.

## Run on macOS (Codex Desktop)

Typical Mac workflow:

```bash
# Terminal 1 — proxy
cd ~/projects/oxpipe
source .venv/bin/activate
export OXPIPE_MODELS=gpt-5.5,gpt-5.6
oxpipe serve
```

Open the dashboard in Safari/Chrome: **http://127.0.0.1:47822/**

Edit **`~/.codex/config.toml`** (same path on macOS as Linux):

```toml
model = "gpt-5.6"
openai_base_url = "http://127.0.0.1:47822/v1"
```

Then **fully quit Codex** (Codex menu → Quit, or `Cmd+Q`) and reopen it so the config reloads.

Confirm:

```bash
# Terminal 2
tail -f ~/.oxpipe/events.jsonl
# use Codex; you should see /v1/responses rows appear
```

macOS notes:

- Use `127.0.0.1`, not `localhost`, if anything fails to connect (IPv6 `::1` quirks).
- Local firewall prompts: allow Python/oxpipe inbound on port **47822** if macOS asks.
- Events and config live under your home directory: `~/.oxpipe/`, `~/.codex/`.
- `oxpipe doctor` checks fonts + prints the dashboard URL.

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
