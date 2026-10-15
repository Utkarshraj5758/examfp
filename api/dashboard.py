"""Build a self-contained static HTML dashboard for examfp.

No server, no network, no external assets: :func:`build_dashboard` is a pure
function that turns collected results into one HTML string.  The side-effecting
:func:`collect` (runs a live trace + robustness sweep) and the file write live
here per the project convention that side effects stay in ``cli`` / ``api``.

Run it with ``python -m api.dashboard [paper.json] [--encrypt]``. This module
depends on the core library, never the other way round.
"""

from __future__ import annotations

import html
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from eval.bench import BenchRow, run_bench
from examfp.attacks import crop, retype, typos
from examfp.cli import ensure_codebook, render_text, vault_from_env, verdict_lines
from examfp.decode.read import read_leak
from examfp.decode.score import score
from examfp.models import Paper

Codebook = dict[int, dict[tuple[str, str], int]]


@dataclass(frozen=True)
class DemoTrace:
    centre: int
    leak_text: str
    positions_read: int
    positions_total: int
    outcome: str
    margin: float
    top5: list[tuple[int, float, bool]]  # (centre, score, is_true)
    verdict: list[str]  # plain-language verdict, shared wording with the CLI


@dataclass(frozen=True)
class DashboardData:
    n_centres: int
    positions_per_paper: int
    codebook_size: int
    durable_fraction: float
    bench: list[BenchRow]
    demo: DemoTrace


def collect(
    paper: Paper,
    codebook: Codebook,
    seed: int = 0,
    n_trials: int = 100,
) -> DashboardData:
    """Run a live demo trace and a robustness sweep for the dashboard."""
    rng = random.Random(seed)
    centre = rng.choice(list(codebook))
    leak = typos(retype(crop(render_text(paper, codebook[centre]), 6, rng)), 0.03, rng)
    result = score(read_leak(leak, paper), codebook)
    top5 = [(cid, sc, cid == centre) for cid, sc in result.ranked[:5]]
    demo = DemoTrace(
        centre=centre,
        leak_text=leak,
        positions_read=result.positions_used,
        positions_total=len(paper.positions()),
        outcome=result.outcome.value,
        margin=result.margin,
        top5=top5,
        verdict=verdict_lines(result),
    )
    report = paper.capacity_report(n_centres=len(codebook), c=3, eps=1e-6)
    bench = run_bench(paper, codebook, k_values=range(1, 9), n_trials=n_trials, seed=seed)
    return DashboardData(
        n_centres=len(codebook),
        positions_per_paper=len(paper.positions()),
        codebook_size=paper.codebook_size(),
        durable_fraction=report.durable_fraction,
        bench=bench,
        demo=demo,
    )


def _bars_svg(bench: list[BenchRow]) -> str:
    width, height, pad = 560, 220, 34
    n = len(bench)
    bw = (width - 2 * pad) / n
    bars = []
    for i, row in enumerate(bench):
        x = pad + i * bw
        h = row.correct_rate * (height - 2 * pad)
        y = height - pad - h
        bars.append(
            f'<rect x="{x + bw * 0.15:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" '
            f'height="{h:.1f}" rx="3" fill="var(--accent)"></rect>'
        )
        bars.append(
            f'<text x="{x + bw / 2:.1f}" y="{height - pad + 15:.1f}" '
            f'text-anchor="middle" class="ax">{row.k}</text>'
        )
        bars.append(
            f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
            f'class="val">{100 * row.correct_rate:.0f}</text>'
        )
    grid = []
    for pct in (0, 25, 50, 75, 100):
        gy = height - pad - pct / 100 * (height - 2 * pad)
        grid.append(f'<line x1="{pad}" y1="{gy:.1f}" x2="{width - pad}" y2="{gy:.1f}" class="grid"></line>')
        grid.append(f'<text x="{pad - 6}" y="{gy + 3:.1f}" text-anchor="end" class="ax">{pct}</text>')
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="correct identification rate by questions leaked">'
        f'{"".join(grid)}{"".join(bars)}'
        f'<text x="{width / 2:.0f}" y="{height - 6}" text-anchor="middle" class="cap">'
        f"questions leaked (k)</text></svg>"
    )


def _table_rows(bench: list[BenchRow]) -> str:
    out = []
    for r in bench:
        out.append(
            "<tr>"
            f"<td>{r.k}</td><td>{100 * r.identified_rate:.1f}</td>"
            f"<td>{100 * r.correct_rate:.1f}</td><td>{100 * r.insufficient_rate:.1f}</td>"
            f'<td class="{"bad" if r.false_id_rate else "good"}">{100 * r.false_id_rate:.1f}</td>'
            f"<td>{r.mean_positions:.1f}</td></tr>"
        )
    return "".join(out)


def _top5_rows(top5: list[tuple[int, float, bool]]) -> str:
    out = []
    for rank, (cid, sc, is_true) in enumerate(top5, start=1):
        mark = ' <span class="true">← true</span>' if is_true else ""
        cls = ' class="hit"' if is_true else ""
        out.append(f"<tr{cls}><td>{rank}</td><td>{cid}{mark}</td><td>{sc:.2f}</td></tr>")
    return "".join(out)


def build_dashboard(data: DashboardData) -> str:
    """Return a self-contained HTML dashboard (pure function)."""
    d = data.demo
    verdict_cls = "good" if d.outcome == "IDENTIFIED" and any(t[2] for t in d.top5) else "warn"
    erased = d.positions_total - d.positions_read
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>examfp dashboard</title>
<style>
  :root {{
    --bg:#fbfbfd; --card:#ffffff; --ink:#1c2024; --muted:#6b7280;
    --line:#e6e8eb; --accent:#3b82f6; --good:#15803d; --bad:#b91c1c; --warn:#b45309;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:28px 20px 56px; }}
  h1 {{ font-size:22px; margin:0 0 2px; }}
  .sub {{ color:var(--muted); margin:0 0 22px; }}
  .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:22px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
  .card .n {{ font-size:22px; font-weight:650; }}
  .card .l {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:18px; margin-bottom:22px; }}
  .panel h2 {{ font-size:15px; margin:0 0 12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ text-align:right; padding:6px 8px; border-bottom:1px solid var(--line); }}
  th:first-child,td:first-child {{ text-align:left; }}
  .good {{ color:var(--good); }} .bad {{ color:var(--bad); font-weight:650; }}
  .warn {{ color:var(--warn); }}
  tr.hit td {{ background:#f0f7ff; font-weight:600; }}
  .true {{ color:var(--accent); font-weight:600; }}
  .verdict {{ font-size:18px; font-weight:700; }}
  pre.leak {{ background:#0f172a; color:#e2e8f0; border-radius:10px; padding:14px;
    overflow:auto; font:12.5px/1.45 ui-monospace,Menlo,Consolas,monospace; white-space:pre-wrap; }}
  svg {{ width:100%; height:auto; }} .grid {{ stroke:var(--line); }}
  .ax {{ fill:var(--muted); font-size:11px; }} .val {{ fill:var(--ink); font-size:11px; }}
  .cap {{ fill:var(--muted); font-size:12px; }}
  .qr {{ color:var(--muted); font-style:italic; margin-top:10px; }}
  .note {{ color:var(--muted); font-size:13px; margin-top:8px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
  @media(max-width:760px){{ .cards{{grid-template-columns:repeat(2,1fr);}} .grid2{{grid-template-columns:1fr;}} }}
</style></head>
<body><div class="wrap">
  <h1>examfp — exam-paper fingerprinting</h1>
  <p class="sub">Trace a leaked paper back to its centre, even cropped and retyped.</p>

  <div class="cards">
    <div class="card"><div class="n">{data.n_centres:,}</div><div class="l">centres</div></div>
    <div class="card"><div class="n">{data.positions_per_paper}</div><div class="l">positions / paper</div></div>
    <div class="card"><div class="n">{data.codebook_size:.1e}</div><div class="l">codebook size</div></div>
    <div class="card"><div class="n">{100 * data.durable_fraction:.0f}%</div><div class="l">durable bits</div></div>
  </div>

  <div class="grid2">
    <div class="panel">
      <h2>Robustness: correct identification vs questions leaked</h2>
      {_bars_svg(data.bench)}
    </div>
    <div class="panel">
      <h2>Sweep ({data.bench[0].trials} single-source leaks / k)</h2>
      <table>
        <thead><tr><th>k</th><th>ident%</th><th>correct%</th><th>insuff%</th>
          <th>false-id%</th><th>mean pos</th></tr></thead>
        <tbody>{_table_rows(data.bench)}</tbody>
      </table>
      <p class="note">false-id% here covers single-source leaks only. Leaks combined
        from several centres are measured separately (NOTES.md, M5.5): in that
        benchmark the decision rule named no innocent centre (0 of 800 colluded
        leaks), at the cost of refusing more often. Measured, not proved.</p>
    </div>
  </div>

  <div class="panel">
    <h2>Live trace — leaked paper (6 questions, retyped, 3% typos)</h2>
    <div class="grid2">
      <div>
        <pre class="leak">{html.escape(d.leak_text)}</pre>
      </div>
      <div>
        <p class="verdict {verdict_cls}">{d.outcome} &middot; margin {d.margin:.2f}</p>
        <p class="note">{"<br>".join(html.escape(line) for line in d.verdict)}</p>
        <p>true centre <b>{d.centre}</b> &middot; positions read <b>{d.positions_read}</b>
           / erased {erased} (of {d.positions_total})</p>
        <table>
          <thead><tr><th>#</th><th>centre</th><th>score</th></tr></thead>
          <tbody>{_top5_rows(d.top5)}</tbody>
        </table>
        <p class="qr">QR-code baseline: no result (mark absent from retyped text)</p>
      </div>
    </div>
  </div>
</div></body></html>
"""


def write_dashboard(data: DashboardData, path: Path) -> None:
    """Write the dashboard HTML to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_dashboard(data), encoding="utf-8")


app = typer.Typer(add_completion=False, help="Build the static HTML dashboard.")


@app.command()
def main(
    paper_path: Annotated[Path, typer.Argument(help="Path to the paper JSON.")] = Path(
        "data/papers/sample.json"
    ),
    out: Annotated[Path, typer.Option(help="Output HTML file.")] = Path("out/dashboard.html"),
    trials: Annotated[int, typer.Option(help="Sweep trials per k.")] = 100,
    seed: Annotated[int, typer.Option(help="RNG seed.")] = 0,
    encrypt: Annotated[
        bool, typer.Option("--encrypt/--no-encrypt", help="Seal the codebook (key: TRACE_KEK).")
    ] = False,
) -> None:
    """Build a self-contained static HTML dashboard."""
    vault = vault_from_env(encrypt)
    paper = Paper.model_validate_json(paper_path.read_text(encoding="utf-8"))
    book = ensure_codebook(paper, Path("out"), vault)
    write_dashboard(collect(paper, book, seed=seed, n_trials=trials), out)
    typer.echo(f"wrote dashboard to {out}  (open it in a browser)")


if __name__ == "__main__":
    app()
