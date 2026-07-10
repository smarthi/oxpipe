from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from oxpipe import __version__
from oxpipe.config import load_settings, summarize_settings
from oxpipe.events.log import summarize_events
from oxpipe.render.fonts import font_available
from oxpipe.render.pages import render_text_to_pages
from oxpipe.render.profiles import load_profile_map, resolve_profile


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from oxpipe.proxy.app import create_app

    settings = load_settings()
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    app = create_app(settings)
    print(f"oxpipe {__version__} listening on http://{settings.host}:{settings.port}", file=sys.stderr)
    print(f"dashboard http://{settings.host}:{settings.port}/", file=sys.stderr)
    print(
        f"upstream={settings.upstream} models={settings.models or ['off']} "
        f"counterfactual={settings.counterfactual}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    settings = load_settings()
    summary = summarize_events(settings.events_path)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    settings = load_settings()
    ok_font, font_msg = font_available()
    print("config:")
    print(summarize_settings(settings))
    print(f"font: {'ok' if ok_font else 'warn'} — {font_msg}")
    profiles = load_profile_map(settings)
    print(f"profiles loaded: {sorted(profiles)}")
    # upstream reachability (optional)
    try:
        import httpx

        r = httpx.get(
            f"{settings.upstream}/v1/models",
            timeout=5.0,
            headers={"Authorization": "Bearer sk-test"},
        )
        print(f"upstream: reachable (HTTP {r.status_code}; auth may fail)")
    except Exception as exc:
        print(f"upstream: connectivity error ({exc})")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    settings = load_settings()
    text = Path(args.infile).read_text(encoding="utf-8")
    profiles = load_profile_map(settings)
    profile = resolve_profile(args.model, profiles, settings.detail)
    pages = render_text_to_pages(text, profile)
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    for p in pages:
        path = out / f"page-{p.index:02d}-of-{p.total:02d}.png"
        path.write_bytes(p.png)
        print(path)
    print(f"wrote {len(pages)} page(s) model={args.model} detail={profile.detail}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="oxpipe", description="OpenAI GPT-5.5/5.6 text→image context proxy")
    p.add_argument("--version", action="version", version=f"oxpipe {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run local proxy")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=cmd_serve)

    stats = sub.add_parser("stats", help="summarize ~/.oxpipe/events.jsonl")
    stats.set_defaults(func=cmd_stats)

    doctor = sub.add_parser("doctor", help="check config/fonts/upstream")
    doctor.set_defaults(func=cmd_doctor)

    render = sub.add_parser("render", help="render a text file to PNG pages")
    render.add_argument("--in", dest="infile", required=True)
    render.add_argument("--out", dest="outdir", required=True)
    render.add_argument("--model", default="gpt-5.6")
    render.set_defaults(func=cmd_render)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
