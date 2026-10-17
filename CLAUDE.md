# TRACE — project conventions

> Claude Code reads this at the start of every session. It is the contract.

## What this is

**TRACE: Adversarially Trained Transformer-Based Decoding for Paraphrase-Robust
Content Fingerprinting of Examination Question Papers.**

Every examination centre receives a question paper identical in answers and
difficulty to every other centre's, but whose *incidental* content (numeric
groups, unit forms, MCQ option order, wording) is set to a combination unique
to that centre. When a leak appears — photographed, cropped, retyped or
reworded — the system recovers that combination and names the source centre,
with a measured false-identification rate (practical mode) or a provable collusion bound (provable mode).

Two modes exist. Never conflate them in code, docs or claims:

| Mode | Codebook | Guarantee |
|------|----------|-----------|
| `practical` | Reed–Solomon over GF(256), one paper per centre | empirically measured identification rate |
| `provable` | Tardos, multi-paper session | provable collusion bound; not deployable in a single paper |

## Environment

- Windows + PowerShell. Use `.\tasks.ps1 <task>`. There is no `make`.
- PowerShell syntax in every shell command: `;` not `&&`.
- Python 3.11, Node 20, Docker Desktop.
- Run `$env:PYTHONIOENCODING = "utf-8"` before any command that prints ₹ or cm².

## Non-negotiables

1. **Never invent cryptographic or coding-theory constructions.** Reproduce
   published ones (Tardos 2003, Reed–Solomon, AES-GCM, Shamir). If a spec is
   ambiguous, STOP AND ASK rather than improvising an adaptation.
2. **Determinism.** Every function that samples takes an explicit
   `rng: np.random.Generator` or `random.Random`. No global `random`, no
   unseeded shuffle, no `datetime.now()` inside logic (inject a clock).
3. **Erasures are never guesses.** A slot that cannot be read is *absent* from
   the observation set. The decoder must never fall back to "most likely
   variant".
4. **No accusation below threshold.** Outcomes are `IDENTIFIED`,
   `MULTI_SOURCE_SUSPECTED`, `INSUFFICIENT`, `NO_MATCH`. A verdict names at most
   one centre, and only on `IDENTIFIED`. A `MULTI_SOURCE_SUSPECTED` verdict names
   nobody. A ranked list is not a verdict: it is shown only beside `IDENTIFIED`
   or on explicit request. Pair hypotheses are opt-in, never part of a verdict,
   and must carry their measured accuracy whenever shown.
5. **Secrets never touch disk unencrypted and never appear in logs.** Covers
   codebooks, Tardos biases, data keys, KEKs, and raw leak uploads.
6. **Tests first.** Every module has tests mirroring its path. A milestone is
   done only when its acceptance test passes.
7. **Types everywhere.** `ruff check .` and `mypy --strict examfp service ml`
   must be clean before any commit.
8. **No network at runtime** except a local model cache and explicitly
   configured outbound calls. Training may download models; the service may not.

## Definition of done (every change)

- [ ] Tests written before implementation, and passing
- [ ] `.\tasks.ps1 lint` clean
- [ ] Public functions carry a docstring stating the invariant they guarantee
- [ ] No new global state, no new unseeded randomness
- [ ] NOTES.md updated when a design decision or finding came out of the work
- [ ] One logical change per commit; message says what and why

## Repository layout

```
examfp/                 core library — pure, no I/O except render/ocr
  models.py             Paper, Question, Slot, Variant, Answer      [FROZEN]
  render.py             Typst -> PDF, layout invariance             [FROZEN]
  fairness/             difficulty bands + step rule, SymPy answers, NLI
                        equivalence, unit and instruction tables, the ask
                        rule, variant separation, readability
  codebook/             rs.py, tardos.py, assign.py, crypto.py
  decode/               ocr.py, align.py, read.py, score.py, neural.py
  attacks.py            crop, retype, typos, paraphrase, collude
  cli.py                typer entrypoint
ml/                     training code — never imported by the service
  dataset.py            synthetic (leak -> slot values) pair generation
  train_decoder.py      transformer fine-tuning
  adversarial.py        attacker/defender loop
  evaluate.py           baseline vs neural comparison
service/                FastAPI app, routers, auth, jobs, migrations
web/                    React dashboard
eval/                   benchmark sweeps and figures
deploy/                 Dockerfiles, compose, Caddy, CI workflows
docs/                   runbook, threat model, ADRs, API docs
tests/                  mirrors examfp/, ml/, service/
```

`models.py` and `render.py` are **frozen**: change them only on explicit
instruction, never as a side effect of another milestone.

## Architecture rules

- The core library is pure and importable with no database, network or GPU.
- The service layer owns all I/O: DB, queue, filesystem, secrets.
- `ml/` never imports `service/`. The service loads a versioned model artefact
  by path or registry id, nothing more.
- The decoder exposes one interface, `SlotDecoder`, with two implementations:
  `FuzzyDecoder` (baseline) and `NeuralDecoder`. Both satisfy the same contract
  tests. Which one runs is configuration, not code.
- Every trace result records the model version and codebook version used.

## ML discipline

- Split train/val/test **by paper**, never by question — splitting by question
  leaks slot vocabulary across the split and inflates every number.
- Every training run writes a run card: data version, seed, hyperparameters,
  metrics, model hash, git SHA. No run without a card.
- Report the fuzzy baseline on the same test set, in the same table, always.
- Never evaluate on adversarial data generated in the same loop iteration it
  was trained on.
- A result is reportable only if it reproduces from the seed in its run card.
- Fixture labels are never revised to match model output. When a model
  disagrees with a hand label, the model has erred and the error counts against
  its budget. Thresholds are never tuned on the fixture they are judged by.

## Security rules

- Envelope encryption: per-exam AES-GCM data key, wrapped by a KEK from the
  vault interface. The database stores ciphertext plus wrapped key only.
- Codebook is append-only. Corrections are new versions with a reason code.
- Every trace request is logged: actor, time, input hash, model version,
  codebook version, outcome. The log is append-only.
- Role separation: `investigator` can submit a leak and read a verdict, and can
  never read codebook contents. `authority` can generate papers. Nobody can
  read plaintext codewords through the API.
- Uploaded leak files are untrusted: size-capped, type-sniffed, never executed,
  stored outside the web root, deleted on a retention schedule.

## How to work in a session

- One milestone per session. `/clear` between milestones.
- Start by reading this file and the milestone's section in PLAN.md.
- State the files you will touch and the acceptance test *before* writing code.
- If a milestone needs a change to a frozen file or a public interface, STOP
  AND ASK.
- End by ticking PLAN.md checkboxes and adding any finding to NOTES.md.

## Commands

```
.\tasks.ps1 test      # pytest
.\tasks.ps1 lint      # ruff + mypy --strict
.\tasks.ps1 demo      # end-to-end CLI demo
.\tasks.ps1 bench     # evaluation sweeps -> eval/out/
.\tasks.ps1 train     # ml/train_decoder.py with the default config
.\tasks.ps1 up        # docker compose up (api, worker, db, web)
.\tasks.ps1 smoke     # post-deploy smoke test against a running stack
```
