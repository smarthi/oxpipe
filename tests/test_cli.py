from __future__ import annotations

from pathlib import Path

from oxpipe.cli import main


def test_cli_stats_and_doctor(tmp_path: Path, monkeypatch, capsys):
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"ts":"t","applied":true,"baseline_tokens":10,"input_tokens":4,"saved_eff":6,"baseline_eff":10}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OXPIPE_EVENTS", str(events))
    monkeypatch.setenv("OXPIPE_MODELS", "off")
    assert main(["stats"]) == 0
    out = capsys.readouterr().out
    assert "applied" in out

    assert main(["doctor"]) == 0
    doc = capsys.readouterr().out
    assert "config" in doc


def test_cli_render(tmp_path: Path, monkeypatch, capsys):
    infile = tmp_path / "in.txt"
    infile.write_text("hello oxpipe\n" * 20, encoding="utf-8")
    outdir = tmp_path / "pages"
    monkeypatch.setenv("OXPIPE_MODELS", "off")
    assert main(["render", "--in", str(infile), "--out", str(outdir), "--model", "gpt-5.6"]) == 0
    assert list(outdir.glob("*.png"))
    assert "wrote" in capsys.readouterr().out
