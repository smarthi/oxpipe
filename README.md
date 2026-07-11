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
# funded platform key required (ChatGPT login is not enough through oxpipe)
export OPENAI_API_KEY=sk-...
```

## Use with Codex Desktop

oxpipe fronts **`https://api.openai.com`**. That path needs a **funded OpenAI platform API key** (`OPENAI_API_KEY`). ChatGPT / Codex subscription login is **not** enough.

Why: ChatGPT OAuth tokens work on Codex’s own backend (`chatgpt.com/backend-api/...`), but they lack the `api.responses.write` scope required by `POST /v1/responses`. Pointing Codex at oxpipe with only ChatGPT login yields:

```text
401 Unauthorized — Missing scopes: api.responses.write
```

(often with a `cf-ray` header from OpenAI’s edge, forwarded through oxpipe)

Codex Desktop also does **not** reliably pick up a shell `OPENAI_BASE_URL`. Configure everything in **user-level** `~/.codex/config.toml` (project-local `.codex/config.toml` ignores provider / base URL keys).

### 1. Create and fund an API key

1. Create a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Ensure the org has billing / credits at [platform.openai.com/settings/organization/billing](https://platform.openai.com/settings/organization/billing)
3. Without funding you may still see oxpipe dashboard hits, then Codex errors like **“you have hit your usage limit”**

Export for CLI clients:

```bash
export OPENAI_API_KEY="sk-..."
```

**macOS Codex Desktop** does not read `~/.zshrc`. Give the Dock/Spotlight app the key, then fully restart Codex:

```bash
launchctl setenv OPENAI_API_KEY "sk-..."
# then Cmd+Q Codex and reopen
```

Or launch Codex from a shell that already has the variable:

```bash
export OPENAI_API_KEY="sk-..."
open -a "Codex"   # app name may vary (ChatGPT / Codex)
```

### 2. Start oxpipe with imaging allowlisted

Default `OXPIPE_MODELS=off` still proxies, but **does not log events or bump dashboard counters**. Allowlist the model you use (GPT-5.5 is fine):

```bash
cd ~/projects/oxpipe
source .venv/bin/activate
export OXPIPE_MODELS=gpt-5.5,gpt-5.6
oxpipe serve
```

Dashboard: http://127.0.0.1:47822/  
(You can also flip model chips there; keep the compression kill switch **on**.)

### 3. Point Codex at oxpipe (`~/.codex/config.toml`)

Use a **custom provider** with `env_key = "OPENAI_API_KEY"` (required name — not `OPEN_API_KEY`):

```toml
model = "gpt-5.5"
model_provider = "oxpipe"

[model_providers.oxpipe]
name = "oxpipe"
base_url = "http://127.0.0.1:47822/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
```

Match `model` to whatever Desktop actually offers (e.g. `gpt-5.5` only). Remove any leftover:

```toml
# do not use with ChatGPT-only login — causes api.responses.write 401
# openai_base_url = "http://127.0.0.1:47822/v1"
```

### 4. Restart Codex Desktop

Fully quit (**Cmd+Q** / Codex → Quit) and reopen so it reloads `config.toml` and picks up `OPENAI_API_KEY`.

If Desktop reports the env key missing, the GUI process still cannot see `OPENAI_API_KEY` — redo the `launchctl setenv` / shell-launch step above.

### 5. Confirm traffic and savings

Use a **Codex** coding session (plain ChatGPT chat in the same app often never hits `~/.codex/config.toml`).

Then check:

- Dashboard: Requests / Imaged counters, recent `/v1/responses` rows, `saved_eff`
- `tail -f ~/.oxpipe/events.jsonl` — look for `applied: true`, `baseline_source: "input_tokens.count"`

Example of a healthy imaged turn: baseline tens of thousands of tokens with a large positive `saved_eff`.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| `Missing scopes: api.responses.write` | ChatGPT login + oxpipe / `openai_base_url`; switch to funded `OPENAI_API_KEY` + custom provider |
| `OPENAI_API_KEY` / env key not found | Desktop launched without the env var; use `launchctl setenv` or launch from a shell |
| “Hit your usage limit” | Unfunded / over-budget API org, or ChatGPT Codex plan caps if not on API key |
| oxpipe running but dashboard stays at 0 | `OXPIPE_MODELS=off` (passthrough not logged); allowlist `gpt-5.5` or toggle chips |
| Codex works, dashboard empty | Requests never reach `127.0.0.1:47822` — wrong config file, still on ChatGPT chat, or didn’t Cmd+Q |
| Warm prompts, tiny Saved % | Expected when almost everything is cached; savings show on large uncached / history slabs |

Bail out: dashboard kill switch, or remove `model_provider = "oxpipe"` and restart Codex.

### macOS notes

- Prefer `127.0.0.1` over `localhost` (IPv6 `::1` quirks).
- Allow Python/oxpipe on port **47822** if the firewall prompts.
- Events / config: `~/.oxpipe/`, `~/.codex/`.
- `oxpipe doctor` checks fonts and prints the dashboard URL.
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
