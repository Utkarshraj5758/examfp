"""Command-line entry point for the crude end-to-end trace.

``python -m examfp.cli generate <paper.json> --centres N --out DIR`` writes one
``centre_<id>.txt`` per centre (the paper rendered as text for that centre's
symbol vector) plus ``codebook.json``.
"""

from __future__ import annotations

import random
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer

from examfp.attacks import crop, retype, typos
from examfp.codebook.assign import assign, load_codebook, save_codebook
from examfp.codebook.tardos import TardosCode, bits_per_paper, simulate_pirate
from examfp.decode.read import read_leak
from examfp.decode.score import score
from examfp.models import Paper

app = typer.Typer(add_completion=False, help="examfp end-to-end trace.")


@app.callback()
def main() -> None:
    """examfp end-to-end trace (crude: no Tardos/RS/crypto/ML)."""


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
    seed: Annotated[int, typer.Option(help="Affine scramble offset.")] = 0,
) -> None:
    """Generate per-centre text papers and a codebook."""
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    codebook = assign(paper, centres, seed)
    for centre, symbols in codebook.items():
        (out / f"centre_{centre}.txt").write_text(
            render_text(paper, symbols), encoding="utf-8"
        )
    save_codebook(codebook, out / "codebook.json")
    typer.echo(f"wrote {len(codebook)} centre files + codebook.json to {out}")


@app.command()
def trace(
    leak_path: Annotated[Path, typer.Argument(help="Path to the leaked paper text.")],
    codebook: Annotated[Path, typer.Option(help="Path to codebook.json.")],
    paper: Annotated[Path, typer.Option(help="Path to the paper JSON.")],
) -> None:
    """Trace a leaked paper back to its centre."""
    paper_model = Paper.model_validate_json(paper.read_text(encoding="utf-8"))
    book = load_codebook(codebook)
    leak = leak_path.read_text(encoding="utf-8")

    observations = read_leak(leak, paper_model)
    result = score(observations, book)

    total = len(paper_model.positions())
    read = result.positions_used
    typer.echo(f"outcome: {result.outcome.value}   margin: {result.margin:.2f}")
    typer.echo(f"positions read: {read} / erased: {total - read} (of {total})")
    typer.echo("top 5 centres:")
    for centre, sc in result.ranked[:5]:
        typer.echo(f"  centre {centre}: {sc:.2f}")
    typer.echo("recovered positions:")
    for (qid, slot), (symbol, conf) in observations.items():
        typer.echo(f"  {qid}::{slot} = {symbol} (conf {conf:.2f})")


def _centre_symbols(paper: Paper, centre: int, seed: int = 0) -> dict[tuple[str, str], int]:
    return assign(paper, centre + 1, seed)[centre]


@app.command()
def leak(
    paper_path: Annotated[Path, typer.Argument(help="Path to the paper JSON.")],
    centre: Annotated[int, typer.Option(help="Centre id to leak.")],
    questions: Annotated[int, typer.Option(help="Questions to keep (crop).")] = 6,
    typos_rate: Annotated[float, typer.Option("--typos", help="Typo swap rate.")] = 0.03,
    retype_leak: Annotated[
        bool, typer.Option("--retype/--no-retype", help="Retype the leak.")
    ] = True,
    out: Annotated[Path, typer.Option(help="Output leak file.")] = Path("leak.txt"),
    seed: Annotated[int, typer.Option(help="Attack RNG seed.")] = 0,
) -> None:
    """Forge a degraded leak of one centre's paper (crude codebook path)."""
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    rng = random.Random(seed)
    text = render_text(paper, _centre_symbols(paper, centre))
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
) -> None:
    """Tell the whole story: generate, leak, trace, and report."""
    start = time.perf_counter()
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))

    out_dir = Path("out")
    codebook_path = out_dir / "codebook.json"
    if not codebook_path.exists():
        typer.echo("out/ missing -> generating 1000 centres ...")
        book = assign(paper, 1000, seed=0)
        out_dir.mkdir(parents=True, exist_ok=True)
        for c, symbols in book.items():
            (out_dir / f"centre_{c}.txt").write_text(
                render_text(paper, symbols), encoding="utf-8"
            )
        save_codebook(book, codebook_path)
    book = load_codebook(codebook_path)

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
    typer.echo("top 5 centres:")
    for rank, (cid, sc) in enumerate(result.ranked[:5], start=1):
        marker = "  <- true" if cid == centre else ""
        typer.echo(f"  {rank}. centre {cid}: {sc:.2f}{marker}")
    typer.echo(f"verdict: {result.outcome.value}   margin: {result.margin:.2f}")
    typer.echo(f"elapsed: {elapsed_ms:.0f} ms")
    typer.echo("QR-code baseline: no result (mark absent from retyped text)")


@app.command()
def dashboard(
    paper_path: Annotated[Path, typer.Argument(help="Path to the paper JSON.")] = Path(
        "data/papers/sample.json"
    ),
    out: Annotated[Path, typer.Option(help="Output HTML file.")] = Path("out/dashboard.html"),
    trials: Annotated[int, typer.Option(help="Sweep trials per k.")] = 100,
    seed: Annotated[int, typer.Option(help="RNG seed.")] = 0,
) -> None:
    """Build a self-contained static HTML dashboard."""
    from api.dashboard import collect, write_dashboard

    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    codebook_path = Path("out") / "codebook.json"
    if not codebook_path.exists():
        typer.echo("out/ missing -> generating 1000 centres ...")
        book = assign(paper, 1000, seed=0)
        codebook_path.parent.mkdir(parents=True, exist_ok=True)
        for c, symbols in book.items():
            (codebook_path.parent / f"centre_{c}.txt").write_text(
                render_text(paper, symbols), encoding="utf-8"
            )
        save_codebook(book, codebook_path)
    book = load_codebook(codebook_path)

    data = collect(paper, book, seed=seed, n_trials=trials)
    write_dashboard(data, out)
    typer.echo(f"wrote dashboard to {out}  (open it in a browser)")


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
