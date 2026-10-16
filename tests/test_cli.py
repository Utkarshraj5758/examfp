"""Tests for the examfp CLI end-to-end trace."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from examfp.cli import app
from examfp.decode.score import PAIR_HYPOTHESIS_CORRECT, PAIR_HYPOTHESIS_NAMED

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
def _collusion_trace(
    tmp_path: Path, size: int, wanted: str, extra: tuple[str, ...] = ()
) -> tuple[str, Path, Path, list[int]]:
    """Trace full-paper hybrids of `size` centres until the output contains `wanted`."""
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
    for seed in range(30):
        rng = random.Random(seed)
        group = rng.sample(range(1000), size)
        leak.write_text(render_text(paper, collude([book[c] for c in group], rng)),
                        encoding="utf-8")
        result = runner.invoke(app, ["trace", str(leak), "--codebook",
                                     str(out / "codebook.json"), "--paper", SAMPLE, *extra])
        if wanted in result.output:
            return result.output, leak, out / "codebook.json", group
    raise AssertionError(f"no seed produced {wanted!r}")


def _no_accusation(output: str) -> None:
    text = output.lower()
    for word in ("accused", "guilty", "leaked by", "identified -"):
        assert word not in text


def test_default_trace_names_nobody_for_a_multi_source_leak(tmp_path: Path) -> None:
    output, leak, codebook, pair = _collusion_trace(
        tmp_path, 2, "is the only pair", extra=("--hypotheses",)
    )
    plain = runner.invoke(app, ["trace", str(leak), "--codebook", str(codebook),
                                "--paper", SAMPLE]).output
    verdict = plain[plain.index("verdict:"):]
    assert "MULTI_SOURCE_SUSPECTED" in verdict and "No centre is named." in verdict
    assert "{" not in verdict and "hypothesis (--hypotheses)" not in plain
    _no_accusation(plain)


def test_hypotheses_flag_prints_the_pair_with_its_measured_accuracy(tmp_path: Path) -> None:
    output, _leak, _codebook, pair = _collusion_trace(
        tmp_path, 2, "is the only pair", extra=("--hypotheses",)
    )
    assert f"{{{min(pair)}, {max(pair)}}}" in output
    assert f"{PAIR_HYPOTHESIS_CORRECT} of {PAIR_HYPOTHESIS_NAMED}" in output
    assert "3 or more centres" in output
    assert "cannot distinguish a two-centre leak from a larger one" in output
    assert "not an accusation" in output
    _no_accusation(output)


def test_hypothesis_lines_wording() -> None:
    from examfp.cli import hypothesis_lines

    none = "\n".join(hypothesis_lines(None))
    assert "nobody is named" in none and "{" not in none
    named = "\n".join(hypothesis_lines((3, 17)))
    assert "{3, 17}" in named and f"{PAIR_HYPOTHESIS_CORRECT} of {PAIR_HYPOTHESIS_NAMED}" in named
    assert "cannot distinguish a two-centre leak from a larger one" in named


def test_trace_never_names_three_or_more(tmp_path: Path) -> None:
    output, *_rest = _collusion_trace(tmp_path, 3, "MULTI_SOURCE_SUSPECTED")
    verdict = output[output.index("verdict:"):]
    assert "No centre is named." in verdict and "{" not in verdict
    _no_accusation(output)


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


def test_multi_source_verdict_lists_causes_and_asserts_no_collusion() -> None:
    from examfp.cli import verdict_lines
    from examfp.decode.score import Outcome, ScoreResult

    result = ScoreResult(ranked=[(5, 1.0)], margin=0.0, positions_used=20,
                         outcome=Outcome.MULTI_SOURCE_SUSPECTED, consistent=0, tolerance=0)
    text = "\n".join(verdict_lines(result))
    assert "no single centre in this codebook explains the observed slots" in text
    assert "more than one centre" in text  # cause 1: multiple sources
    assert "misreads beyond the gate tolerance (0 mismatching slots)" in text  # cause 2
    assert "outside this codebook" in text  # cause 3
    assert "most likely" not in text  # it must not assert collusion
    assert "No centre is named." in text


# --- display: a ranking only where the verdict already names a centre ---------------------------
DISTINCT = 900_000  # centre ids 900000-900999: no count, symbol or score can mimic them


def _distinct_id_codebook(tmp_path: Path) -> tuple[Path, dict[int, dict[tuple[str, str], int]]]:
    from examfp.codebook.assign import assign, dumps_codebook
    from examfp.models import Paper

    paper = Paper.model_validate_json(Path(SAMPLE).read_text(encoding="utf-8"))
    book = {DISTINCT + c: symbols for c, symbols in assign(paper, 1000, seed=0).items()}
    path = tmp_path / "codebook.json"
    path.write_text(dumps_codebook(book), encoding="utf-8")
    return path, book


def _leak_text(kind: str, book: dict[int, dict[tuple[str, str], int]]) -> str:
    import random

    from examfp.attacks import collude
    from examfp.cli import render_text
    from examfp.models import Paper

    paper = Paper.model_validate_json(Path(SAMPLE).read_text(encoding="utf-8"))
    if kind == "MULTI_SOURCE_SUSPECTED":  # full paper mixed from two centres
        rng = random.Random(0)
        return render_text(paper, collude([book[DISTINCT + 1], book[DISTINCT + 2]], rng))
    if kind == "INSUFFICIENT":  # one question: too few slots to name anyone
        return "\n".join(render_text(paper, book[DISTINCT + 1]).splitlines()[3:5])
    return "Lorem ipsum dolor sit amet, consectetur adipiscing elit."  # NO_MATCH


def _trace_output(tmp_path: Path, kind: str, *extra: str) -> tuple[str, list[int]]:
    codebook, book = _distinct_id_codebook(tmp_path)
    leak = tmp_path / "leak.txt"
    leak.write_text(_leak_text(kind, book), encoding="utf-8")
    result = runner.invoke(
        app, ["trace", str(leak), "--codebook", str(codebook), "--paper", SAMPLE, *extra]
    )
    assert result.exit_code == 0, result.output
    assert f"outcome: {kind}" in result.output
    return result.output, [c for c in book if str(c) in result.output]


@pytest.mark.parametrize("kind", ["MULTI_SOURCE_SUSPECTED", "NO_MATCH", "INSUFFICIENT"])
def test_default_output_names_no_centre_unless_identified(tmp_path: Path, kind: str) -> None:
    output, shown = _trace_output(tmp_path, kind)
    assert shown == [], f"centre identifiers in the default {kind} output: {shown[:5]}"
    assert "top 5" not in output and "margin" not in output  # nothing that looks like a ranking


def test_hypotheses_flag_reveals_the_ranking_labelled_as_not_a_verdict(tmp_path: Path) -> None:
    output, shown = _trace_output(tmp_path, "MULTI_SOURCE_SUSPECTED", "--hypotheses")
    assert "ranked scores (--hypotheses) - not a verdict:" in output
    assert shown  # the ranking is there, on request
    assert "No centre is named." in output  # the verdict itself is unchanged


def test_ranking_is_shown_only_with_an_identified_verdict_or_on_request() -> None:
    from examfp.cli import show_ranking
    from examfp.decode.score import Outcome

    for outcome in Outcome:
        assert show_ranking(outcome) is (outcome is Outcome.IDENTIFIED)
        assert show_ranking(outcome, hypotheses=True)
