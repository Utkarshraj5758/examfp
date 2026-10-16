# TRACE — engineering notes

Findings and design decisions, newest milestone last. Every number here was
measured on the sample paper (`data/papers/sample.json`: 8 questions,
31 fingerprint positions) unless stated otherwise.

---

## Phase 0 findings (M1–M3, Sept 2026)

### F1 — Capacity: one paper cannot carry a provable code

Tardos (2003) needs code length `m = ceil(100 * c^2 * ln(n/eps))`, constant kept
literally. The sample paper offers **31 positions** (59.5 payload bits; 51 Tardos
bits after taking `floor(log2(alphabet))` per position).

Required positions, `n = 500` centres:

| c | eps = 1e-2 | eps = 1e-3 | eps = 1e-6 |
|---|-----------:|-----------:|-----------:|
| 2 | 4,328 | 5,249 | 8,012 |
| 3 | 9,738 | 11,810 | 18,027 |
| 5 | 27,049 | 32,806 | 50,075 |

No cell is reachable. At `eps = 1e-6` the sample supports `c_max = 0.12`; a
realistic 60-question paper (~3.9 positions/question, ~232 positions) reaches
only `c_max = 0.34` — not even one colluder. Multi-paper layering makes the
length representable: at `n = 500, c = 3, eps = 1e-6` a centre's codeword is
18,028 bits = **354 papers per session** at 51 bits/paper. In a coin-strategy
collusion demo the accuser caught all three colluders and accused no innocent.

**Consequence:** two modes that must never be conflated — see
[ADR 0001](docs/ADR/0001-two-modes.md). The empirical constant `k` is still
`<unset>`; PLAN.md assigns its measurement to M11.

### F2 — Channel durability: what a leaker copies vs. what they rewrite

Fingerprint channels split by whether a leaker reproduces them verbatim:

| channel | durable? | positions | bits |
|---|---|---:|---:|
| numeric groups | yes — numbers are copied exactly | 5 | 14.0 |
| MCQ option order | yes — order is copied exactly | 3 | 20.7 |
| unit forms (`km/h` vs `kilometres per hour`) | yes — copied literally | 4 | 5.8 |
| wording (`Calculate` vs `Work out`) | **no** — paraphrase destroys it | 19 | 19.0 |

Durable fraction **68.1%** (target ≥ 60%). It got there by widening numeric
groups to 6–7 variants *inside* their difficulty bands, using 5-option MCQs
(5! − 1 = 119 permutations, identity excluded) and making wording binary.

- Difficulty bands cap numeric alphabets (a 1-digit non-trivial divisor allows at
  most 7 variants), so durable capacity grows mainly through option order.
- Positions and bits are different budgets: Tardos length is counted in
  positions, codebook size in bits. 19 of 31 positions are fragile wording.
- `attacks.typos` only swaps adjacent letters, so the numeric payload survives
  typos verbatim; `retype` keeps digits, option lines and units.
- Implication for M8–M10: under paraphrase, wording positions become erasures.
  The neural decoder must be judged on durable-channel recovery first.

### F3 — Mixed-radix assignment is position-dependent

The crude `assign` expands `x = (c*617 + 37 + seed) mod prod(alphabets)` in mixed
radix with the **last** position least significant. For 1,000 centres
`x < ~617,000`, far below `prod(alphabets) ~ 8e17`, so the high-order positions
never change. Measured: **20 of 31 positions — all of q1–q5 and 2 of q6's 5 —
hold the same symbol for every one of the 1,000 centres.** Only 11 positions
(the rest of q6, plus q7 and q8) discriminate, so **identification depends on
which questions leak**: a q1-only leak ties all 1,000 centres (`INSUFFICIENT`).

Crop → retype → 3% typos, 200 trials per `k` (`eval/out/results.csv`, seed 0):

| k leaked | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| correct % | 0.0 | 9.5 | 27.5 | 53.5 | 71.0 | 91.0 | 100 | 100 |
| false-id % | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Over seeds 0–99 the 6-question rate is 88/100; the misses are crops that drop
the late questions, and they come back `INSUFFICIENT`, never a wrong centre.
Recovery averages ~3.8 positions per leaked question.

**Fix (M5):** Reed–Solomon over GF(256) is MDS — any `k` symbols determine the
codeword — so every position carries information and accuracy should stop
depending on which questions leak. M5 must report accuracy by leaked-question
position, before vs after.

**Status: fixed in M5.** No position is constant any more, and early, middle and
late leaks perform alike — see the M5 section below.

### Smaller Phase 0 notes

- PDF text extraction inserts or drops spaces around kerned pairs (`AV` → `A V`);
  any test that round-trips text through a PDF must compare whitespace-insensitively.
- Question text is emitted as Typst string literals (`#"..."`), which disables
  smart quotes and `--` dash substitution; only `\` and `"` need escaping.

---

## M4 — repo hardening (2026-10-15)

- **numpy pin.** numpy 2.5 requires Python ≥ 3.12, so the 3.11 contract pins
  **numpy 2.4.6**. The whole pinned set, all extras together, was resolved with
  wheels only for Python 3.11 and 3.12 on Windows (74 / 73 packages).
- **Packaging bug fixed.** `packages = ["examfp"]` shipped only the top-level
  package; `examfp.codebook` and `examfp.decode` were missing from built wheels
  (editable installs hid it, and so does a stale `build/` directory — verify
  with a clean build). Now discovered with `packages.find`; guarded by
  `tests/test_repo_hygiene.py`. The wheel now holds exactly `examfp`,
  `examfp.codebook`, `examfp.decode`, `ml`, `service`.
- **Line endings.** Git for Windows sets `core.autocrlf=true` in its system
  gitconfig, so Windows clones — CI included — get CRLF files. The suite is
  green on a CRLF clone. Git-for-Windows `grep` strips CR, so check endings with
  `git ls-files --eol`, not grep.
- **Acceptance record.** Clean clone → fresh `.venv` → `pip install -e ".[dev]"`
  → `.\tasks.ps1 lint` clean and `.\tasks.ps1 test` 110 passed, on Python
  3.12.10 (clean export) and 3.11.17 (real `git clone`, CRLF).
  `pre-commit run --all-files` green. CI has not run yet: the project is not a
  git repository and has no remote.
- **Execution policy.** Windows 11 defaults to `Restricted`, which blocks
  `.\tasks.ps1`. Allow local scripts once with
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or run one task with
  `powershell -ExecutionPolicy Bypass -File .\tasks.ps1 test`.
- **`ml/` and `service/`** exist as empty packages so the contract's
  `mypy --strict examfp service ml` runs exactly as written.
- **Pre-commit hooks are local** (`language: system`): they run the pinned
  ruff/mypy from the active environment. Isolated hook environments would drift
  from the pins and lack the dependencies mypy needs.

### Open items found during M4 (not fixed — out of scope)

- **Plaintext codebook on disk.** `generate`, `demo` and `dashboard` write
  `out/codebook.json` unencrypted, violating security rule 5. `.gitignore`
  keeps it out of git, but the real fix is envelope encryption (M12).
  *M5: partly resolved — `--encrypt` writes only an AES-GCM envelope. Plaintext
  is still the default so the demo runs with zero setup.*
- **Layout drift.** `api/dashboard.py` and `eval/` predate the CLAUDE.md layout
  (`service/`, `web/`). `examfp/cli.py`'s `dashboard` command imports
  `api.dashboard`, so the core library reaches into repo tooling — against
  "the core library is pure". Resolve when M12/M13 replace the dashboard.
  *M5: dependency inverted — the command moved to `python -m api.dashboard` and
  a hygiene test forbids `examfp/` importing repo tooling. `api/` and `eval/`
  still predate the layout.*
- **Stale placeholder text.** `Paper.capacity_report` prints
  `k = <unset> (... pending M6)`, but PLAN.md now assigns measuring `k` to M11.
  `models.py` is frozen; correct it in M11 under explicit instruction.
  *M5: fixed on explicit instruction (one string in `models.py`).*

### Deferred dependency choices

Pinned only what CLAUDE.md / PLAN.md name unambiguously. Chosen later, in the
milestone that needs them: worker framework (Celery vs RQ, M12), JWT library
(M12), ~~AES-GCM library and whether it lives in core or service~~ (decided in
M5: `cryptography` in core, as CLAUDE.md places `crypto.py` there), SymPy
(M6), DeBERTa tokenizer extras such as `sentencepiece`/`protobuf` (M6/M9), OCR
engines (M7), plotting for figures (M10/M11), and a transitive lock file.

---

## M5 — Reed–Solomon codebook (2026-10-15)

**Codec.** `examfp/codebook/rs.py`: RS over GF(256), QR-code parameters
(primitive polynomial 0x11D, alpha = 2, first root alpha^0), systematic
encoding, Forney erasure decoding, standard library only. It reproduces three
published vectors (ISO/IEC 18004 "HELLO WORLD" and "01234567" 1-M, Wikiversity
"RS codes for coders"), each cross-checked against the independent `reedsolo`.
Hypothesis: any `k` surviving symbols recover the codeword; a corrupted survivor
is refused, never absorbed.

**Packing** ([ADR 0002](docs/ADR/0002-rs-slot-packing.md)). Each GF(256) symbol is
a group of slots read in mixed radix, with capacity >= 256 (injective) and a
most-significant place value <= 255 (every slot varies). The sample paper gives
**n = 7** symbols; 1,000 centres need **k = 2**, so up to 5 symbols may be lost.
`assign` keeps its signature. No position is constant over 1,000 centres
(previously 20 of 31).

### Before / after (sample paper, 1,000 centres, retype + 3% typos, 200 trials per cell)

Random crop of `k` questions — correct identification:

| k | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| mixed-radix (before) | 0.0 | 9.5 | 27.5 | 53.5 | 71.0 | 91.0 | 100 | 100 |
| Reed–Solomon (after) | 1.5 | 91.0 | 99.5 | 100 | 100 | 100 | 100 | 100 |

Leaks drawn only from one third of the paper — correct identification:

| region (questions) | k | mixed-radix | Reed–Solomon |
|---|--:|--:|--:|
| early (q1–q3) | 1 / 2 / 3 | 0 / 0 / 0 | 1.0 / 94.5 / 100 |
| middle (q4–q6) | 1 / 2 / 3 | 0 / 0 / 0 | 2.0 / 90.0 / 100 |
| late (q7–q8) | 1 / 2 | 0 / 100 | 1.0 / 99.0 |

False identification is **0% in every cell, for both codebooks**. Every miss is
`INSUFFICIENT`. The mixed-radix k-sweep reproduces the Phase 0 numbers exactly,
confirming the baseline was preserved verbatim. Raw data: `eval/out/results.csv`,
`eval/out/results_by_region.csv` (`.\tasks.ps1 bench`, ~30 s).

**Findings.**
- Position dependence is gone: before, early or middle leaks were worthless at
  any size; now every third performs alike.
- **One question is still not enough, by arithmetic, not by code.** A question
  offers at most a few hundred slot combinations (q1: 168, q2: 476) for 1,000
  centres, so several centres share any one of them. Two questions reach about
  90%; three, 100%.
- The trace still scores slots against every centre (`score.py`) rather than
  decoding RS directly. RS supplies the spread and distance; direct erasure
  decoding (`complete_symbols`) needs `k` *intact* groups, and groups span
  questions (ADR 0002).

### Decisions

- **Crypto randomness.** Data keys and nonces come from `os.urandom`, the one
  deliberate exception to the seeded-RNG rule: seeded keys would be predictable.
  The source is injectable so tests stay deterministic.
- **Envelope design.** Fresh AES-256-GCM data key per envelope, wrapped by the
  vault's KEK (also AES-256-GCM). Associated data binds format, KEK id and
  purpose. `EnvVault` is the dev stub (`TRACE_KEK`, base64 of 32 bytes); M12 adds
  a real vault behind the same `Vault` protocol. Generate a dev key with
  `python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"`.
- **`cryptography==50.0.2`** pinned in core, resolved with wheels for Python 3.11
  and 3.12 on Windows alongside every other pin. No cipher is implemented here.

### Bugs the new codebook exposed (fixed)

- `leak` rebuilt one centre as `assign(paper, centre + 1)[centre]`. That was
  only valid for the per-centre mixed-radix code; RS codewords depend on the
  total centre count. `leak` now takes `--centres` (default 1000, as `generate`).
- `demo`/`dashboard` reused any codebook already in `out/`, including a pre-M5
  one, and reported the old behaviour. They now refuse a codebook that is not the
  current demo codebook and say to delete `out/`; they never overwrite it.
- `tasks.ps1` was an advanced script (because of `[Parameter()]` attributes),
  so forwarded arguments starting `--out` collided with `-OutVariable` /
  `-OutBuffer`. It now uses a plain `param()` and passes `$args` through.

### Open items

- **Codebook versioning.** Codebook files carry no scheme or version metadata,
  so staleness is detected only by comparing with the demo codebook. CLAUDE.md
  requires every trace to record the codebook version: add a versioned header
  (M12).
- **Rendered papers are codebook-equivalent.** Each `out/centre_*.txt` reveals
  that centre's codeword, so the full set reveals the codebook even when it is
  encrypted. Treat rendered papers as secrets: delete after printing, and
  encrypt or keep them in the service in M12.
- **Plaintext by default.** `--encrypt` is opt-in; flip the default once a
  vault is part of normal setup (M12).
