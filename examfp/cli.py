"""Command-line entry point: generate papers, forge leaks, trace them.

``python -m examfp.cli generate <paper.json> --centres N --out DIR`` writes one
``centre_<id>.txt`` per centre (the paper rendered as text for that centre's
symbol vector) plus the codebook. By default the codebook is only ever written
as an AES-GCM envelope (``codebook.json.enc``, key from ``TRACE_KEK``), and
``trace``/``demo`` decrypt it in memory; ``--plaintext`` opts out, with a
warning naming the file. ``demo`` and the dashboard still write a plaintext demo
codebook unless given ``--encrypt``. Side effects live here; the
library modules stay pure. The dashboard lives in ``api/`` (``python -m
api.dashboard``) so this package depends on no repo tooling.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer

from examfp.attacks import crop, retype, typos
from examfp.codebook.assign import Codebook, assign, dumps_codebook, loads_codebook
from examfp.codebook.crypto import (
    DecryptionError,
    EnvVault,
    Vault,
    VaultError,
    is_sealed,
    open_sealed,
    seal,
)
from examfp.codebook.tardos import TardosCode, bits_per_paper, simulate_pirate
from examfp.decode.read import read_leak
from examfp.decode.score import (
    MIN_READ_SLOTS,
    PAIR_HYPOTHESIS_CORRECT,
    PAIR_HYPOTHESIS_NAMED,
    Outcome,
    ScoreResult,
    score,
    unique_pair_hypothesis,
)
from examfp.models import Paper

app = typer.Typer(add_completion=False, help="examfp end-to-end trace.")


@app.callback()
def main() -> None:
    """examfp: generate fingerprinted papers, forge leaks, trace them."""


CODEBOOK_PLAIN = "codebook.json"
CODEBOOK_SEALED = "codebook.json.enc"
_PURPOSE = "codebook"


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(code=2)


def vault_from_env(encrypt: bool) -> Vault | None:
    """Return the env-var vault when encrypting; exit cleanly if its key is unusable."""
    if not encrypt:
        return None
    try:
        return EnvVault.from_environ(os.environ)
    except VaultError as exc:
        raise _fail(str(exc)) from None


def write_codebook(book: Codebook, directory: Path, vault: Vault | None) -> Path:
    """Write the codebook into ``directory``; with a vault, only an envelope touches disk."""
    directory.mkdir(parents=True, exist_ok=True)
    if vault is None:
        path = directory / CODEBOOK_PLAIN
        path.write_text(dumps_codebook(book), encoding="utf-8")
    else:
        path = directory / CODEBOOK_SEALED
        path.write_bytes(seal(dumps_codebook(book).encode("utf-8"), vault, purpose=_PURPOSE))
    return path


def read_codebook(path: Path) -> Codebook:
    """Read a plaintext or sealed codebook; sealed ones are decrypted in memory only."""
    data = path.read_bytes()
    if not is_sealed(data):
        return loads_codebook(data.decode("utf-8"))
    try:
        vault = EnvVault.from_environ(os.environ)
        return loads_codebook(open_sealed(data, vault, purpose=_PURPOSE).decode("utf-8"))
    except (VaultError, DecryptionError) as exc:
        raise _fail(str(exc)) from None


def write_centre_papers(paper: Paper, book: Codebook, directory: Path) -> None:
    """Render every centre's paper to ``centre_<id>.txt`` in ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    for centre, symbols in book.items():
        (directory / f"centre_{centre}.txt").write_text(
            render_text(paper, symbols), encoding="utf-8"
        )


def ensure_codebook(paper: Paper, directory: Path, vault: Vault | None) -> Codebook:
    """Load the 1,000-centre demo codebook from ``directory``, generating it if missing.

    Guarantees: never silently uses a codebook built by an older scheme (for
    example the pre-M5 mixed-radix one), and never overwrites it - it exits with
    instructions instead.
    """
    expected = assign(paper, 1000, seed=0)
    path = directory / (CODEBOOK_PLAIN if vault is None else CODEBOOK_SEALED)
    if not path.exists():
        typer.echo(f"{path} missing -> generating 1000 centres ...")
        write_centre_papers(paper, expected, directory)
        write_codebook(expected, directory, vault)
        return expected
    if read_codebook(path) != expected:
        raise _fail(
            f"{path} was not built by the current codebook scheme (1,000 centres, seed 0, "
            f"Reed-Solomon). Delete {directory} to regenerate it."
        )
    return expected


def render_text(paper: Paper, symbols: Mapping[tuple[str, str], int]) -> str:
    """Render ``paper`` as plain text for one centre's symbol vector."""
    lines = [paper.title, "=" * len(paper.title), ""]
    for number, question in enumerate(paper.questions, start=1):
        q_symbols = {s.name: symbols[(question.id, s.name)] for s in question.slots}
        text, _letter = question.resolve(q_symbols)
        label = "mark" if question.marks == 1 else "marks"
        body = text.replace("\n", "\n   ")
        lines.append(f"{number}. {body}   [{question.marks} {label}]")
        lines.append("")
    return "\n".join(lines)


@app.command()
def generate(
    paper_path: Annotated[Path, typer.Argument(help="Path to the paper JSON.")],
    centres: Annotated[int, typer.Option(help="Number of centres to generate.")] = 1000,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
    seed: Annotated[int, typer.Option(help="Codebook seed (picks centre messages).")] = 0,
    plaintext: Annotated[
        bool,
        typer.Option("--plaintext", help="Opt out of encryption: write codebook.json in clear "
                     "(a secret on disk; prints a warning naming the file)."),
    ] = False,
) -> None:
    """Generate per-centre text papers and a codebook, sealed unless ``--plaintext``.

    Guarantees: by default only an AES-GCM envelope (key from ``TRACE_KEK``) is
    written, and a missing or unusable key stops the command before anything is
    written; ``--plaintext`` writes ``codebook.json`` and warns, naming the file.
    """
    vault = None if plaintext else _sealing_vault()  # fail before writing anything
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    codebook = assign(paper, centres, seed)
    write_centre_papers(paper, codebook, out)
    path = write_codebook(codebook, out, vault)
    typer.echo(f"wrote {len(codebook)} centre files + {path.name} to {out}")
    if vault is None:
        typer.echo(f"warning: wrote a PLAINTEXT codebook to {path}. It is a secret "
                   "(CLAUDE.md rule 5); delete it once sealed, or omit --plaintext.", err=True)
    elif (out / CODEBOOK_PLAIN).exists():
        typer.echo(f"warning: an earlier plaintext {CODEBOOK_PLAIN} is still in {out}",
                   err=True)


def _sealing_vault() -> Vault:
    """The vault ``generate`` seals with by default; exits, naming the opt-out, if unusable."""
    try:
        return EnvVault.from_environ(os.environ)
    except VaultError as exc:
        raise _fail(f"{exc}. Codebooks are sealed by default: set TRACE_KEK, or pass "
                    "--plaintext to write an unencrypted codebook.") from None


@app.command()
def trace(
    leak_path: Annotated[Path, typer.Argument(help="Path to the leaked paper text.")],
    codebook: Annotated[
        Path, typer.Option(help="Path to codebook.json or codebook.json.enc.")
    ],
    paper: Annotated[Path, typer.Option(help="Path to the paper JSON.")],
    hypotheses: Annotated[
        bool,
        typer.Option(
            "--hypotheses/--no-hypotheses",
            help="Investigative output, never a verdict: the ranked scores for any "
            "outcome and, for MULTI_SOURCE_SUSPECTED, the pair hypothesis with its "
            "measured accuracy.",
        ),
    ] = False,
) -> None:
    """Trace a leaked paper back to its centre."""
    paper_model = Paper.model_validate_json(paper.read_text(encoding="utf-8"))
    book = read_codebook(codebook)
    leak = leak_path.read_text(encoding="utf-8")

    observations = read_leak(leak, paper_model)
    result = score(observations, book)

    total = len(paper_model.positions())
    read = result.positions_used
    ranking = show_ranking(result.outcome, hypotheses)
    margin = f"   margin: {result.margin:.2f}" if ranking else ""
    typer.echo(f"outcome: {result.outcome.value}{margin}")
    typer.echo(f"positions read: {read} / erased: {total - read} (of {total})")
    if ranking:
        typer.echo("top 5 centres:" if result.outcome is Outcome.IDENTIFIED
                   else "ranked scores (--hypotheses) - not a verdict:")
        for rank, (centre, sc) in enumerate(result.ranked[:5]):
            tag = "  (consistent)" if rank < result.consistent else ""
            typer.echo(f"  centre {centre}: {sc:.2f}{tag}")
    typer.echo("recovered positions:")
    for (qid, slot), (symbol, conf) in observations.items():
        typer.echo(f"  {qid}::{slot} = {symbol} (conf {conf:.2f})")
    typer.echo(
        f"consistent centres: {result.consistent} (tolerance {result.tolerance} "
        f"mismatching slots; read floor {MIN_READ_SLOTS} slots)"
    )
    for line in verdict_lines(result):
        typer.echo(line)
    if hypotheses:
        if result.outcome is Outcome.MULTI_SOURCE_SUSPECTED:
            for line in hypothesis_lines(unique_pair_hypothesis(observations, book)):
                typer.echo(line)
        else:
            typer.echo(f"hypothesis (--hypotheses): not applicable - the outcome is "
                       f"{result.outcome.value}.")


def show_ranking(outcome: Outcome, hypotheses: bool = False) -> bool:
    """Whether a ranked list of centres may be displayed.

    Guarantees: by default a ranking appears only beside an ``IDENTIFIED``
    verdict, where the named centre already is the verdict. For every other
    outcome it appears only on explicit request (``--hypotheses``), so rank 1 is
    never on screen as a stand-in for a verdict the decision rule did not reach.
    """
    return outcome is Outcome.IDENTIFIED or hypotheses


def verdict_lines(result: ScoreResult) -> list[str]:
    """Plain-language verdict.

    Guarantees: only ``IDENTIFIED`` names a centre. ``MULTI_SOURCE_SUSPECTED``
    names nobody, asserts no collusion, and lists its three possible causes.
    """
    if result.outcome is Outcome.IDENTIFIED:
        return [
            f"verdict: IDENTIFIED - centre {result.ranked[0][0]} is the only centre "
            f"consistent with every slot read (margin {result.margin:.2f})."
        ]
    if result.outcome is Outcome.MULTI_SOURCE_SUSPECTED:
        lines = [
            "verdict: MULTI_SOURCE_SUSPECTED - no single centre in this codebook explains "
            "the observed slots.",
            "  Possible causes: (1) the leak combines papers from more than one centre;",
            "  (2) misreads beyond the gate tolerance "
            f"({result.tolerance} mismatching slots);",
            "  (3) the leak comes from a paper outside this codebook.",
            "  No centre is named.",
        ]
        return lines
    if result.outcome is Outcome.INSUFFICIENT:
        return ["verdict: INSUFFICIENT - the evidence does not single out any centre."]
    return ["verdict: NO_MATCH - nothing in the text matched the paper."]


def hypothesis_lines(pair: tuple[int, int] | None) -> list[str]:
    """Wording for the opt-in pair hypothesis (``trace --hypotheses``).

    Guarantees: a reported pair is always printed with its measured accuracy, the
    statement that a two-centre leak cannot be told from a larger one, and the
    statement that it is not an accusation.
    """
    if pair is None:
        return [
            "hypothesis (--hypotheses): no single pair of centres uniquely explains the "
            "slots read; nobody is named."
        ]
    a, b = pair
    return [
        f"hypothesis (--hypotheses): {{{a}, {b}}} is the only pair of centres that jointly "
        "explains the slots read.",
        f"  Measured accuracy: {PAIR_HYPOTHESIS_CORRECT} of {PAIR_HYPOTHESIS_NAMED} such pairs "
        "were correct (collusion benchmark, sample paper);",
        "  every wrong pair came from a leak involving 3 or more centres.",
        "  The system cannot distinguish a two-centre leak from a larger one, so either",
        "  centre may have taken no part.",
        "  This is a hypothesis for investigation, not an accusation.",
    ]


def _centre_symbols(paper: Paper, centre: int, n_centres: int) -> dict[tuple[str, str], int]:
    # The RS codebook depends on the total centre count (message length k and the
    # sampled messages), so forge from the same codebook `generate` would build.
    if not 0 <= centre < n_centres:
        raise _fail(f"centre {centre} is outside 0..{n_centres - 1}")
    return assign(paper, n_centres, seed=0)[centre]


@app.command()
def leak(
    paper_path: Annotated[Path, typer.Argument(help="Path to the paper JSON.")],
    centre: Annotated[int, typer.Option(help="Centre id to leak.")],
    centres: Annotated[
        int, typer.Option(help="Centres in the generated codebook (as for generate).")
    ] = 1000,
    questions: Annotated[int, typer.Option(help="Questions to keep (crop).")] = 6,
    typos_rate: Annotated[float, typer.Option("--typos", help="Typo swap rate.")] = 0.03,
    retype_leak: Annotated[
        bool, typer.Option("--retype/--no-retype", help="Retype the leak.")
    ] = True,
    out: Annotated[Path, typer.Option(help="Output leak file.")] = Path("leak.txt"),
    seed: Annotated[int, typer.Option(help="Attack RNG seed.")] = 0,
) -> None:
    """Forge a degraded leak of one centre's paper (practical-mode codebook)."""
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    rng = random.Random(seed)
    text = render_text(paper, _centre_symbols(paper, centre, centres))
    text = crop(text, questions, rng)
    if retype_leak:
        text = retype(text)  # a leaker retypes first, then fat-fingers typos
    text = typos(text, typos_rate, rng)
    out.write_text(text, encoding="utf-8")
    typer.echo(f"wrote leak of centre {centre} ({questions} questions) to {out}")


@app.command()
def demo(
    paper_path: Annotated[Path, typer.Argument(help="Path to the paper JSON.")] = Path(
        "data/papers/sample.json"
    ),
    seed: Annotated[int, typer.Option(help="RNG seed (centre + attack).")] = 0,
    encrypt: Annotated[
        bool, typer.Option("--encrypt/--no-encrypt", help="Seal the codebook (key: TRACE_KEK).")
    ] = False,
) -> None:
    """Tell the whole story: generate, leak, trace, and report."""
    start = time.perf_counter()
    vault = vault_from_env(encrypt)
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    book = ensure_codebook(paper, Path("out"), vault)

    rng = random.Random(seed)
    centre = rng.choice(list(book.keys()))
    text = render_text(paper, book[centre])
    leak_text = typos(retype(crop(text, 6, rng)), 0.03, rng)  # retype, then typos

    observations = read_leak(leak_text, paper)
    result = score(observations, book)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    total = len(paper.positions())
    read = result.positions_used
    typer.echo("=== leaked text (6 questions, retyped, 3% typos) ===")
    typer.echo(leak_text)
    typer.echo("")
    typer.echo(f"true centre: {centre}")
    typer.echo(f"positions read: {read} / erased: {total - read} (of {total})")
    if show_ranking(result.outcome):
        typer.echo("top 5 centres:")
        for rank, (cid, sc) in enumerate(result.ranked[:5], start=1):
            marker = "  <- true" if cid == centre else ""
            typer.echo(f"  {rank}. centre {cid}: {sc:.2f}{marker}")
    for line in verdict_lines(result):
        typer.echo(line)
    typer.echo(f"elapsed: {elapsed_ms:.0f} ms")
    typer.echo("QR-code baseline: no result (mark absent from retyped text)")


@app.command()
def tardos(
    paper_path: Annotated[Path, typer.Argument(help="Path to the paper JSON.")],
    centres: Annotated[int, typer.Option(help="Number of centres (n).")] = 100,
    collusion: Annotated[int, typer.Option(help="Collusion bound (c).")] = 3,
    eps: Annotated[float, typer.Option(help="Error probability (eps).")] = 0.01,
    seed: Annotated[int, typer.Option(help="RNG seed.")] = 0,
) -> None:
    """Build a Tardos code and run a self-contained accusation demo."""
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    code = TardosCode.build(paper, centres, collusion, eps, seed)

    typer.echo(
        f"Tardos code: m={code.m} bits, threshold Z={code.threshold:.1f}, "
        f"t={code.t:.5f}"
    )
    typer.echo(
        f"layering: {bits_per_paper(paper)} bits/paper -> "
        f"k={code.k} papers per centre session"
    )
    coalition = list(range(min(collusion, centres)))
    pirate = simulate_pirate(code, coalition, seed=seed + 1, strategy="coin")
    accused = code.accuse(pirate)
    typer.echo(f"demo coalition {coalition} (marking assumption, coin strategy):")
    typer.echo(f"  accused: {accused}")
    caught = sorted(set(accused) & set(coalition))
    innocents_accused = sorted(set(accused) - set(coalition))
    typer.echo(f"  colluders caught: {caught}   innocents accused: {innocents_accused}")


if __name__ == "__main__":
    app()
