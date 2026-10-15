"""Tests for the examfp CLI end-to-end trace."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from examfp.cli import app

runner = CliRunner()
SAMPLE = str(Path(__file__).resolve().parents[1] / "data" / "papers" / "sample.json")


def test_generate_writes_files_and_codebook(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["generate", SAMPLE, "--centres", "25", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    files = sorted(out.glob("centre_*.txt"))
    assert len(files) == 25
    assert (out / "codebook.json").exists()


def test_two_centres_differ(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", SAMPLE, "--centres", "25", "--out", str(out)])
    a = (out / "centre_0.txt").read_text(encoding="utf-8")
    b = (out / "centre_1.txt").read_text(encoding="utf-8")
    assert a != b


def test_trace_identifies_centre(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", SAMPLE, "--centres", "100", "--out", str(out)])
    # Build a leak from the tail of a known centre's rendered paper.
    full = (out / "centre_42.txt").read_text(encoding="utf-8").splitlines()
    leak = tmp_path / "leak.txt"
    leak.write_text("\n".join(full[-12:]), encoding="utf-8")

    result = runner.invoke(
        app,
        ["trace", str(leak), "--codebook", str(out / "codebook.json"), "--paper", SAMPLE],
    )
    assert result.exit_code == 0, result.output
    assert "IDENTIFIED" in result.output
    assert "centre 42:" in result.output
    assert "positions read:" in result.output
    assert "recovered positions:" in result.output


def test_leak_command_writes_degraded_file(tmp_path: Path) -> None:
    leak = tmp_path / "leak.txt"
    result = runner.invoke(
        app,
        ["leak", SAMPLE, "--centre", "42", "--questions", "6", "--typos", "0.03",
         "--retype", "--out", str(leak), "--seed", "1"],
    )
    assert result.exit_code == 0, result.output
    text = leak.read_text(encoding="utf-8")
    assert text == text.lower()  # retyped
    assert text.count("\n\n") == 5  # six question blocks


def test_demo_tells_the_story(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "papers").mkdir(parents=True)
    (tmp_path / "data" / "papers" / "sample.json").write_text(
        Path(SAMPLE).read_text(encoding="utf-8"), encoding="utf-8"
    )
    result = runner.invoke(app, ["demo", "--seed", "12"])
    assert result.exit_code == 0, result.output
    assert "verdict:" in result.output
    assert "positions read:" in result.output
    assert "top 5 centres:" in result.output
    assert "QR-code baseline: no result (mark absent from retyped text)" in result.output
    assert "elapsed:" in result.output


def test_tardos_command_reports_and_catches(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["tardos", SAMPLE, "--centres", "60", "--collusion", "2", "--eps", "0.05"],
    )
    assert result.exit_code == 0, result.output
    assert "Tardos code: m=" in result.output
    assert "papers per centre session" in result.output
    assert "colluders caught:" in result.output
