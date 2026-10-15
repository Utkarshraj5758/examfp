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


# --- M5: encrypted codebooks, leak/codebook consistency ---------------------------------------
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # base64 of bytes 0..31 (test only)
WRONG_KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="


def _no_plaintext_codebook_anywhere(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            assert path.name != "codebook.json", f"plaintext codebook at {path}"
            assert b'"q1::intro"' not in path.read_bytes(), f"codebook content in {path}"


def test_generate_encrypt_never_writes_plaintext_codebook(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["generate", SAMPLE, "--centres", "25", "--out", str(out), "--encrypt"],
        env={"TRACE_KEK": KEY},
    )
    assert result.exit_code == 0, result.output
    assert (out / "codebook.json.enc").exists()
    assert len(list(out.glob("centre_*.txt"))) == 25
    _no_plaintext_codebook_anywhere(tmp_path)


def test_generate_encrypt_without_key_fails_before_writing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["generate", SAMPLE, "--centres", "5", "--out", str(out), "--encrypt"],
        env={"TRACE_KEK": None},
    )
    assert result.exit_code != 0
    assert "TRACE_KEK" in result.output
    assert not out.exists() or not any(out.iterdir())  # nothing written


def test_trace_decrypts_encrypted_codebook_in_memory(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(
        app, ["generate", SAMPLE, "--centres", "100", "--out", str(out), "--encrypt"],
        env={"TRACE_KEK": KEY},
    )
    leak = tmp_path / "leak.txt"
    leak.write_text(
        "\n".join((out / "centre_42.txt").read_text(encoding="utf-8").splitlines()[-12:]),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["trace", str(leak), "--codebook", str(out / "codebook.json.enc"), "--paper", SAMPLE],
        env={"TRACE_KEK": KEY},
    )
    assert result.exit_code == 0, result.output
    assert "IDENTIFIED" in result.output and "centre 42:" in result.output
    _no_plaintext_codebook_anywhere(tmp_path)  # decrypted in memory only


def test_trace_with_wrong_key_fails_cleanly(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(
        app, ["generate", SAMPLE, "--centres", "10", "--out", str(out), "--encrypt"],
        env={"TRACE_KEK": KEY},
    )
    leak = tmp_path / "leak.txt"
    leak.write_text("anything", encoding="utf-8")
    result = runner.invoke(
        app,
        ["trace", str(leak), "--codebook", str(out / "codebook.json.enc"), "--paper", SAMPLE],
        env={"TRACE_KEK": WRONG_KEY},
    )
    assert result.exit_code != 0
    assert "authentication" in result.output
    assert WRONG_KEY not in result.output and KEY not in result.output
    assert "Traceback" not in result.output


def test_leak_forges_the_centre_of_the_generated_codebook(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", SAMPLE, "--centres", "100", "--out", str(out)])
    leak = tmp_path / "leak.txt"
    result = runner.invoke(
        app,
        ["leak", SAMPLE, "--centre", "42", "--centres", "100", "--questions", "8",
         "--typos", "0", "--no-retype", "--out", str(leak)],
    )
    assert result.exit_code == 0, result.output
    traced = runner.invoke(
        app, ["trace", str(leak), "--codebook", str(out / "codebook.json"), "--paper", SAMPLE]
    )
    assert "IDENTIFIED" in traced.output
    assert "centre 42:" in traced.output.splitlines()[3]  # top-ranked centre


def test_demo_refuses_a_stale_codebook(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from eval.baselines import mixed_radix_assign
    from examfp.codebook.assign import save_codebook
    from examfp.models import Paper

    paper = Paper.model_validate_json(Path(SAMPLE).read_text(encoding="utf-8"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "out").mkdir()
    save_codebook(mixed_radix_assign(paper, 1000), tmp_path / "out" / "codebook.json")
    result = runner.invoke(app, ["demo", SAMPLE])
    assert result.exit_code != 0
    assert "current codebook scheme" in result.output
    assert "Traceback" not in result.output


# --- M5.5: collusion hypothesis wording --------------------------------------------------------
def test_trace_reports_collusion_as_a_hypothesis_never_an_accusation(tmp_path: Path) -> None:
    import random

    from examfp.attacks import collude
    from examfp.cli import render_text
    from examfp.codebook.assign import assign
    from examfp.models import Paper

    paper = Paper.model_validate_json(Path(SAMPLE).read_text(encoding="utf-8"))
    out = tmp_path / "out"
    runner.invoke(app, ["generate", SAMPLE, "--centres", "1000", "--out", str(out)])
    book = assign(paper, 1000, seed=0)
    leak = tmp_path / "leak.txt"
    for seed in range(20):  # a 2-centre hybrid of the full paper usually yields a hypothesis
        rng = random.Random(seed)
        pair = rng.sample(range(1000), 2)
        leak.write_text(render_text(paper, collude([book[c] for c in pair], rng)), encoding="utf-8")
        result = runner.invoke(
            app, ["trace", str(leak), "--codebook", str(out / "codebook.json"), "--paper", SAMPLE]
        )
        if "COLLUSION_SUSPECTED" in result.output:
            break
    else:
        raise AssertionError("no seed produced a collusion hypothesis")
    text = result.output.lower()
    assert "hypothesis" in text and "not an accusation" in text
    for word in ("accused", "guilty", "leaked by", "identified centre"):
        assert word not in text
    assert all(str(c) in result.output for c in pair)


def test_trace_shows_gate_evidence(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", SAMPLE, "--centres", "100", "--out", str(out)])
    leak = tmp_path / "leak.txt"
    leak.write_text((out / "centre_7.txt").read_text(encoding="utf-8"), encoding="utf-8")
    result = runner.invoke(
        app, ["trace", str(leak), "--codebook", str(out / "codebook.json"), "--paper", SAMPLE]
    )
    assert result.exit_code == 0, result.output
    assert "consistent centres: 1" in result.output
    assert "read floor" in result.output
