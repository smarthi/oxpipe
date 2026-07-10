# oxpipe — Design Spec

**Status:** MVP implemented (v0.1.0)  
**Date:** 2026-07-10  
**Location:** `/home/smarthi/projects/oxpipe`

## 1. One-liner

A Python local proxy that does for **OpenAI** what [pxpipe](https://github.com/teamchong/pxpipe) does for **Anthropic**: rewrite bulky request context into compact PNGs (plus a text fact-sheet of exact identifiers) so vision billing undercuts dense text tokens.

Primary targets: **GPT-5.5 and GPT-5.6** families over `/v1/responses` and `/v1/chat/completions` (Codex / ChatGPT-integrated clients). Daily-driver posture.

## 1.1 Prior art: pxpipe (not in scope)

[pxpipe](https://github.com/teamchong/pxpipe) already does this for Anthropic. **oxpipe does not support Anthropic models or APIs** — no Claude/Fable/Opus imaging, no `/v1/messages`. Anthropic is mentioned only as the inspiration.

| | pxpipe (separate project) | oxpipe (this repo) |
|---|---|---|
| Provider | Anthropic only | **OpenAI only** |
| Models | Fable, Opus, etc. | **GPT-5.5 and GPT-5.6 only** (first-class) |
| APIs | Anthropic Messages | OpenAI Responses + Chat Completions |
| Language | JS/TS | Python |

We are not forking pxpipe. Same product idea; OpenAI-native implementation.

Other OpenAI model ids may hit the proxy as passthrough; **imaging is first-class only for GPT-5.5 and GPT-5.6** (including suffixes like `-sol` / `-terra`). Pre-5.5 = passthrough-only in v1.

## 2. Decisions (locked)

| Question | Decision |
|---|---|
| Language | **Python 3.11+** |
| Name / path | **oxpipe** at `/home/smarthi/projects/oxpipe` |
| Target models | **OpenAI GPT-5.5 and GPT-5.6 only** |
| Day-one APIs | **Both** `/v1/responses` and `/v1/chat/completions` |
| Product posture | **Daily-driver proxy** (reliability > research novelty) |
| Imaging default | **Proxy on, imaging off** until 5.5/5.6 ids are allowlisted (see §5) |

### Clarifying “imaging default”

The proxy always listens and forwards. Separately, *imaging* (text→PNG rewrite) only runs for models listed in `OXPIPE_MODELS`.

- `OXPIPE_MODELS` unset / `off` → every request is byte-identical passthrough (safe default for a daily driver).
- `OXPIPE_MODELS=gpt-5.5,gpt-5.6` → prefix match for those families (including variant suffixes); everything else still passthrough.

GPT-5.5/5.6 need per-family (and sometimes per-suffix) render profiles and eval before silent default-on. oxpipe ships **allowlist-gated** until our harness clears a variant — then README can recommend e.g. `OXPIPE_MODELS=gpt-5.5,gpt-5.6`.

## 3. Goals

1. Drop uncached input-token cost on dense agent traffic (code, JSON, tool output, long history).
2. Stay transparent to OpenAI clients: set `OPENAI_BASE_URL` (or equivalent) to the proxy; no client forks.
3. Prefer correctness over maximum compression: fact-sheet, live-tail text, fail-open.
4. Make savings auditable: per-request JSONL with text counterfactual vs billed usage.

## 4. Non-goals (v1)

- Anthropic / Claude support of any kind (out of scope — use pxpipe if you need that)
- First-class imaging support for pre-5.5 OpenAI models (passthrough only)
- Web dashboard (CLI + JSONL first; dashboard later if needed)
- Guaranteeing byte-exact OCR from images
- Mutating model outputs / streaming response bodies beyond passthrough
- Training or hosting a custom OCR/vision model

## 5. Safety model (daily-driver)

| Rule | Behavior |
|---|---|
| Allowlist | Imaging only for `OXPIPE_MODELS`; else passthrough |
| Fail open | Render / gate / parse errors → forward original body |
| Live tail | Last `N` turns (default 2–4) always stay text |
| Tools | Tool / function schemas stay native JSON — never imaged |
| Fact-sheet | Extract hex, UUIDs, paths, ports, emails, long numbers → text block beside images |
| Verbatim pin | Blocks matching secret-like patterns or marked keep-text stay text |
| Detail mode | Default image `detail=high` (bounded cost); `original` only via explicit config for experiments |

Silent confabulation of exact strings from images is an accepted residual risk for *gist* workloads (coding agents that re-read files). It is **not** acceptable as the only copy of secrets, SHAs, or auth material — those must remain text via fact-sheet / pin / live tail.

## 6. Architecture

```text
Client (Codex, ChatGPT desktop/integrations, OpenAI SDK, curl)
    │  OPENAI_BASE_URL=http://127.0.0.1:47822/v1
    ▼
┌──────────────────────────────────────────────┐
│ oxpipe                                       │
│  auth passthrough (Bearer)                   │
│  route: /v1/responses | /v1/chat/completions │
│         + passthrough for other /v1/*        │
│  allowlist → transform or forward            │
│  split: slab / old history / live tail       │
│  factsheet extract → render PNG pages        │
│  profitability gate                          │
│  rewrite multimodal content                  │
│  forward upstream → stream response back     │
│  append ~/.oxpipe/events.jsonl               │
└──────────────────────────────────────────────┘
    │
    ▼
api.openai.com (or OXPIPE_UPSTREAM)
```

### Request transform (conceptual)

**Eligible for imaging**

1. Large static slab: system / developer / `instructions` (always considered; live-tail does not protect these)  
2. Large tool / function *results* (not definitions) above a char floor  
3. Older conversation turns behind the live tail, when large enough to clear the gate

**Never imaged**

- Live tail messages  
- Tool/function definitions  
- Small or sparse-prose blocks that fail the gate  
- Non-allowlisted models  

### Wire shapes

**Responses API** — replace eligible text parts with `input_image` (base64 data URL or equivalent) + `input_text` fact-sheet + short instruction banner (“context rendered as images; fact-sheet has exact ids”).

**Chat Completions** — same content as `image_url` data URLs in multimodal `user`/`system` message content arrays. Prefer attaching images on user-role content when the API rejects images in system.

Streaming: proxy must pass SSE / chunked streams through without buffering the full response (request may buffer for rewrite; response must not).

## 7. Profitability gate

Image only when estimated image tokens beat estimated text tokens for that block (and after optional cache-burn adjustment).

**Text estimate:** configurable chars/token (default ~4 for prose, ~1–1.5 for code/JSON density detection).

**Image estimate (OpenAI):**

- Prefer patch formula for GPT-5.x families:  
  `ceil(w/32) * ceil(h/32) * model_multiplier` under the selected `detail` policy  
- Fall back to documented tile/base tables for older vision models  
- Optional live probe via OpenAI input-token count endpoint when configured (accuracy over latency)

**Cache-honest savings (logging only):**

```text
actual_eff   = uncached + cached * cache_read_rate
baseline_eff = text counterfactual under the same cached/uncached split
saved        = baseline_eff - actual_eff   # may be negative; never floor to 0 in logs
```

Do not claim the provider’s cache discount as oxpipe savings.

## 8. Render profiles

Per exact `model` id (longest-prefix match):

| Field | Purpose |
|---|---|
| `cell_w`, `cell_h` | Glyph cell size (larger = safer recall, fewer chars/page) |
| `columns` | Characters per line before wrap |
| `max_height_px` | Page break height |
| `font` | Monospace atlas (e.g. JetBrains Mono / DejaVu Sans Mono) |
| `detail` | OpenAI vision detail for this profile |
| `strip_width_px` | Target image width (≈768 short-side friendly) |

**MVP default profiles:** separate conservative geometries for `gpt-5.5*` and `gpt-5.6*` (larger cells, fewer columns) — bias toward readable gist over max compression. Per-suffix overrides (e.g. `gpt-5.6-sol`) when measured. Tunable via `OXPIPE_PROFILES` without code changes.

Pagination: long text → multiple PNGs; each page gets a header (`page i/n`, instruction banner).

## 9. Fact-sheet extractor

Before render, scan eligible text for high-risk exact tokens:

- 8–64 char hex strings  
- UUIDs  
- Absolute / repo-relative paths  
- Host:port and bare ports in config-like lines  
- Emails, ARNs, API-key-shaped tokens (pin as text; prefer *not* sending secrets upstream at all — out of scope beyond detection)

Emit a compact text block, e.g.:

```text
[oxpipe fact-sheet — exact tokens; prefer these over image OCR]
hex: a1b2c3d4e5f6
path: /srv/app/config/runtime.json
port: 47822
```

Fact-sheet always accompanies imaged content for that request slice.

## 10. Package layout

```text
oxpipe/
  pyproject.toml
  README.md
  SPEC.md                 # this document
  src/oxpipe/
    __init__.py
    __main__.py           # python -m oxpipe
    cli.py                # serve / stats / doctor
    config.py             # env + profile loading
    proxy/
      app.py              # ASGI/HTTP server
      upstream.py         # forward + stream
      routes.py
    transform/
      responses.py
      chat.py
      split.py            # slab / history / tail
      factsheet.py
    render/
      pages.py            # text → PNG bytes
      fonts.py
      profiles.py
    gate/
      estimate.py
      decide.py
    billing/
      openai_tokens.py    # patch/tile estimators
    events/
      log.py              # ~/.oxpipe/events.jsonl
  tests/
  eval/                   # fixture recall / gist / confabulation harness
  configs/
    profiles.default.yaml
```

## 11. Configuration (env)

| Variable | Default | Meaning |
|---|---|---|
| `OXPIPE_HOST` | `127.0.0.1` | Bind address |
| `OXPIPE_PORT` | `47822` | Bind port |
| `OXPIPE_UPSTREAM` | `https://api.openai.com` | Upstream base |
| `OXPIPE_MODELS` | `off` | Comma list of ids/prefixes to image (intended: `gpt-5.5,gpt-5.6`); `off` disables |
| `OXPIPE_LIVE_TAIL` | `3` | Recent turns kept as text |
| `OXPIPE_DETAIL` | `high` | Default vision detail |
| `OXPIPE_PROFILES` | _(file)_ | Path or inline JSON/YAML overrides |
| `OXPIPE_EVENTS` | `~/.oxpipe/events.jsonl` | Event log path |
| `OXPIPE_MIN_CHARS` | `6000` | Min chars before a block is eligible |
| `OPENAI_API_KEY` | _(client/header)_ | Not required on proxy if client sends `Authorization` |

## 12. CLI (MVP)

```bash
oxpipe serve              # start proxy
oxpipe stats              # summarize events.jsonl (saved tokens, apply rate)
oxpipe doctor             # check fonts, upstream reachability, config
oxpipe render --in f.txt --out out/   # debug PNG pages without proxy
```

## 13. Events schema (v1)

One JSON object per transformed or gated request:

```json
{
  "ts": "2026-07-10T19:00:00Z",
  "path": "/v1/responses",
  "model": "gpt-5.6",
  "applied": true,
  "reason": "ok",
  "baseline_tokens": 52000,
  "image_tokens_est": 14000,
  "input_tokens": 18000,
  "cached_tokens": 12000,
  "saved_eff_est": 0.34,
  "pages": 4,
  "latency_ms_transform": 45
}
```

Passthrough / not-allowlisted rows may be sampled or omitted; compressed and `not_profitable` rows should always log.

## 14. MVP build order

1. **Scaffold** — packaging, CLI stub, config, SPEC/README  
2. **Renderer** — text → PNG pages + profile loader  
3. **Fact-sheet** — extractor + unit tests  
4. **Transforms** — Responses + Chat Completions rewrite  
5. **Gate + billing estimators**  
6. **Proxy** — ASGI serve, auth passthrough, streaming upstream  
7. **Events + `oxpipe stats`**  
8. **Eval harness** — exact / gist / confabulation fixtures before recommending any default model  

**Definition of done for “daily driver v1”:**

- Point Codex / Chat Completions clients at the proxy with imaging `off` → identical behavior to direct OpenAI  
- Enable `OXPIPE_MODELS=gpt-5.5,gpt-5.6` → dense sessions show positive `saved_eff_est` without breaking tool calls  
- Failures degrade to passthrough, never 500 the client for transform bugs  
- Eval harness documents recall risk **per family/variant** (5.5 vs 5.6) before README recommends them

## 15. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Silent ID confabulation | Fact-sheet, live tail, allowlist, eval gate before recommending models |
| Warm cache → tiny savings | Honest accounting; docs explain client shape |
| `detail=original` cost blowups | Default `high`; cap page geometry in profiles |
| Latency from PNG encode | Only image large blocks; parallel page encode; skip small requests |
| API shape drift (ChatGPT app) | Dual transformers + passthrough unknown routes; integration tests on fixtures |
| Mini models expensive vision multipliers | Estimator per model family; gate will refuse unprofitable rewrites |

## 16. Out of scope follow-ups

- Browser dashboard (pxpipe-style)  
- Anthropic path  
- Automatic model promotion into defaults after eval pass  
- Surrogate OCR preflight before send  
- History collapse sophistication beyond token-floor + live-tail

---

## Appendix A — Client setup (target UX)

```bash
pip install -e .
oxpipe serve
export OPENAI_BASE_URL=http://127.0.0.1:47822/v1
export OXPIPE_MODELS=off                 # passthrough (safe)
# after eval clears:
# export OXPIPE_MODELS=gpt-5.5,gpt-5.6  # images both families
```

## Appendix B — Prior art

Inspired by [pxpipe](https://github.com/teamchong/pxpipe) (Anthropic). oxpipe is OpenAI-only: GPT-5.5/5.6, Python, Responses + Chat Completions. No Anthropic path.

## Appendix C — GPT-5.5 / 5.6 variant notes

Exact model id selects render profile. Families and suffixes do **not** silently inherit each other’s geometry (`gpt-5.5` ≠ `gpt-5.6` ≠ `gpt-5.6-sol`). MVP ships:

- shared conservative defaults per family (`gpt-5.5`, `gpt-5.6`)
- optional per-suffix overrides in `configs/profiles.default.yaml`

Eval and README recommendations are per allowlist entry, not “all GPT are fine.”
