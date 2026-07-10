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

## Run

```bash
# Safe daily-driver: proxy on, imaging off
export OXPIPE_MODELS=off
oxpipe serve

# Point OpenAI clients at the proxy
export OPENAI_BASE_URL=http://127.0.0.1:47822/v1

# Enable imaging for 5.5 / 5.6 after you accept eval risk
export OXPIPE_MODELS=gpt-5.5,gpt-5.6
```

## CLI

```bash
oxpipe doctor
oxpipe stats
oxpipe render --in notes.txt --out /tmp/oxpipe-pages --model gpt-5.6
```

## Behavior

- Non-allowlisted models → byte-identical passthrough
- Transform errors → fail open (original body forwarded)
- System / `instructions` are eligible even with a live tail; last N chat turns stay text
- Tool schemas stay JSON; large prior text may be imaged when the profitability gate wins (dense code/JSON; sparse short lines often stay text)
- Events: `~/.oxpipe/events.jsonl`

## Tests

```bash
pytest -q
```
