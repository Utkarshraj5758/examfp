# TRACE — build plan

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

**Rule: one milestone per Claude Code session.** Each milestone below carries a
ready-to-paste prompt and an acceptance test. A milestone is not done until its
acceptance test passes, `.\tasks.ps1 lint` is clean, and PLAN.md is ticked.

---

## Phase 0 — Already built (do not rebuild)

- [x] **M1** Data model + Typst renderer (`models.py`, `render.py`) — FROZEN
- [x] **M2** Tardos code, faithful to Tardos (2003), multi-paper layering
- [x] **M3** Crude mixed-radix `assign`, fuzzy decoder, attacks, CLI, benchmark

Measured baseline to beat: **91% identification at 6 leaked questions, 100% at
7+, 0% false identification across 1,600 single-source trials, 37 ms to score
1,000 centres.** *Correction (M5.5): those trials contained no collusion; under
collusion the same rule named innocent centres in up to 55% of leaks. See M5.5.*

---

## Phase 1 — Make it correct (Oct 2026)

### [x] M4 — Repo hardening and task runner

Bring the existing code up to industry hygiene before adding anything.

**Status:** done. Local acceptance passed on Python 3.11 and 3.12
(clean clone, `pip install -e ".[dev]"`, `.\tasks.ps1 test` 110 green, lint
clean); CI green on the pushed commit `7193e8c` (2026-10-15).

**Build:** `pyproject.toml` with pinned deps and extras (`core`, `ml`,
`service`, `dev`); `tasks.ps1`; `.gitignore` (out/, *.pdf, .venv, eval/out,
models/); pre-commit running ruff + mypy; GitHub Actions CI running lint and
tests on push; `NOTES.md` seeded with the three findings from Phase 0;
`docs/ADR/0001-two-modes.md` recording the practical/provable split.

**Acceptance:** a clean clone runs `.\tasks.ps1 test` green; CI passes on a
pushed branch; `pip install -e ".[dev]"` works from scratch.

**Prompt:**
> Read CLAUDE.md. Build M4: packaging and CI hygiene only, no feature work.
> Create pyproject.toml with pinned dependencies and the extras core/ml/service/dev;
> tasks.ps1 implementing test, lint, demo, bench, train, up, smoke; .gitignore;
> a pre-commit config running ruff and mypy --strict; a GitHub Actions workflow
> running lint and tests on push and PR; NOTES.md seeded with the capacity
> finding, the channel-durability finding and the mixed-radix position-dependence
> finding; and docs/ADR/0001-two-modes.md recording the practical vs provable
> split. Do not touch examfp/ logic. Acceptance: clean clone, `pip install -e
> ".[dev]"`, `.\tasks.ps1 test` green, CI green.

---

### [x] M5 — Reed–Solomon codebook (replaces crude assign)

Removes the known weakness: identification currently depends on *which*
questions leak.

**Status:** done (2026-10-15, branch `m5-reed-solomon`). Erasure property tests
and three published vectors pass; no position is constant over 1,000 centres;
the end-to-end trace still names the right centre; early, middle and late leaks
now perform alike (early/middle went from 0% to 100% at 3 questions). Also
delivered: `--encrypt` (AES-GCM envelope), the `api/` dependency inversion, and
the M11 placeholder fix. Numbers in NOTES.md, M5.

**Build:** `codebook/rs.py` — GF(256) arithmetic with log/antilog tables,
systematic RS encoding, erasure decoding via Forney. No dependency; implement
it. Because per-slot alphabets are small (2–119), pack groups of slots into one
GF(256) symbol and document the packing. `codebook/assign.py` rewritten to use
it behind the **unchanged** public signature.

**Acceptance:** property test — for random codewords and random erasure
patterns up to `n−k`, decoding recovers the centre exactly; the end-to-end
`trace` still names the right centre; benchmark shows identification no longer
depends on which questions were cropped (report accuracy by leaked-question
position, before vs after).

**Prompt:**
> Read CLAUDE.md and NOTES.md. Build M5: Reed–Solomon over GF(256) in
> examfp/codebook/rs.py — log/antilog tables, systematic encoding, Forney
> erasure decoding, no new dependency, tested against known vectors. Per-slot
> alphabets are 2–119, so implement and document slot grouping that packs
> several positions into one GF(256) symbol. Rewrite assign.py to use it while
> keeping its public signature unchanged so the CLI and decoder are unaffected.
> Hypothesis property tests: any k symbols with up to n−k erasures recover the
> codeword. Then extend eval/bench.py to report accuracy by which questions
> leaked (early/middle/late), and record the before/after comparison in NOTES.md.

---

### [x] M5.5 — Consistency gate (safety fix, inserted 2026-10-16)

A live safety bug, kept separate from M6: under collusion the margin-only
decision rule named innocent centres (5.5% of 2-centre leaks, 47–55% of 3–5).

**Built:** consistency gate applied before the margin rule; calibrated mismatch
tolerance (`MISREAD_RATE`, `FALSE_REJECTION_BUDGET`) with a documented
recalibration procedure; measured read floor (`MIN_READ_SLOTS = 11`); fourth
outcome `MULTI_SOURCE_SUSPECTED` (whenever the gate empties above the floor; a
pair is named only when exactly one pair explains the reads, as a hypothesis;
sets of 3+ never named); `collude()` attack (2–5 centres, minority strategy);
calibration, floor, bits-floor and collusion rows in `eval/bench.py`; claims
corrected; ADR 0003.

**Status:** done (branch `m5.5-consistency-gate`, stacked on M5). 0 innocents
identified for coalitions of 1–5 after the change; single-source 6-question
leaks unchanged at 200/200; multi-source flagged on 800/800 colluded leaks and
0/200 single-source. Cost: leaks of 1–2 questions no longer name a centre. Open:
named pairs from 3–5-centre leaks include an outsider (11 of 11) — owner to
decide whether pairs are named at all. Numbers in NOTES.md, M5.5.

---

### [ ] M6 — Fairness checker

The claim the whole project rests on, made machine-checkable.

**Build:** `fairness/bands.py` (already partly in models — keep it there, wrap
it), `fairness/answers.py` using SymPy with exact `Rational`, `fairness/nli.py`
using `cross-encoder/nli-deberta-v3-small` requiring bidirectional entailment,
`fairness/readability.py` comparing word count, syllable count and rare-word
count within tolerance. One `FairnessReport` per variant with per-check
pass/fail and reason.

**Acceptance:** on a labelled fixture set of 40 variants (20 fair, 20
deliberately broken — wrong answer, meaning drift, difficulty jump, rare word),
all 20 broken are rejected with at most 2 false rejections. NLI model loads
lazily and scores a pair in under 300 ms on CPU.

**Prompt:**
> Read CLAUDE.md. Build M6, the fairness checker, in examfp/fairness/. Four pure
> check functions each returning (passed: bool, reason: str): answer_equivalent
> using SymPy exact Rationals; meaning_equivalent using cross-encoder/nli-deberta-v3-small
> requiring entailment in both directions above a configurable threshold, model
> loaded lazily and cached; readability_similar on word count, syllable count and
> rare-word count within tolerance; band_satisfied wrapping the existing
> difficulty-band validator. Combine into FairnessReport. First create
> tests/fixtures/variants.json with 20 fair and 20 deliberately broken variants
> covering wrong answer, meaning drift, difficulty jump and rare vocabulary, and
> show me that file before implementing. Acceptance: all 20 broken rejected, at
> most 2 false rejections, NLI under 300 ms per pair on CPU.

---

### [ ] M7 — OCR path

**First task, before the OCR acceptance test runs:** measure the OCR reader's
per-slot misread rate and recalibrate the decision rule against it —
`MISREAD_RATE`, hence the gate tolerance, then `MIN_READ_SLOTS` — using the
procedure in ADR 0003. *Why first:* the gate's tolerance is 0, calibrated for the
fuzzy text reader (0 misreads in 104,026 reads). At tolerance 0, a 1% per-slot
misread rate makes 1 − 0.99¹¹ ≈ 10% of genuine 11-slot leaks fail the gate, and
those leaks would come back `MULTI_SOURCE_SUSPECTED` or `INSUFFICIENT`. That
would look like an OCR failure when it is really a gate calibrated for the wrong
reader.

**Build:** `decode/ocr.py` behind an `OcrBackend` protocol with PaddleOCR and
Tesseract implementations selected by config; normalisation (Unicode forms,
Devanagari→ASCII digits, whitespace, punctuation); integration so `trace`
accepts an image path.

**Acceptance:** a corpus of 20 real phone photographs of printed papers, held
in `tests/data/photos/`, yields ≥90% of slots read correctly; `trace photo.jpg`
names the right centre for at least 18 of 20.

**Prompt:**
> Read CLAUDE.md. Build M7: OCR input. Define an OcrBackend protocol in
> examfp/decode/ocr.py with PaddleOCR and Tesseract implementations chosen by
> config, plus a normalisation step (Unicode NFC, Devanagari to ASCII digits,
> whitespace and punctuation). Wire it so the trace CLI accepts .jpg/.png/.pdf.
> I will supply 20 phone photographs in tests/data/photos/ with their true
> centre ids in a manifest. Acceptance: ≥90% of slots read correctly and ≥18/20
> traced to the right centre. Report per-slot-kind accuracy so we know whether
> numerals or wording suffer more.

---

## Phase 2 — Make it the title (Nov 2026 – Feb 2027)

This is the ML core. It is what makes the project final-year work.

### [ ] M8 — Adversary and dataset

**Build:** `attacks.py` grows an `LlmParaphraser` (local small model or API
behind a flag) producing rewrites at three strength levels: light (synonyms),
medium (clause reordering), heavy (full rewrite, numbers preserved).
`ml/dataset.py` generates (corrupted leak text → true slot symbols) pairs at
scale, split **by paper**, versioned with a hash, written as JSONL.

**Acceptance:** 50,000 pairs generated reproducibly from a seed; a manual audit
of 50 random heavy-paraphrase samples confirms the numbers survive and the
meaning is preserved; the fuzzy baseline's accuracy on this set is measured and
recorded — this is the number the neural decoder must beat.

**Prompt:**
> Read CLAUDE.md and NOTES.md. Build M8: the adversary and the training set.
> Extend examfp/attacks.py with LlmParaphraser producing light, medium and heavy
> rewrites, numbers always preserved, behind an explicit flag so tests run
> offline with a rule-based fallback. Build ml/dataset.py generating
> (corrupted leak text -> true slot symbols) pairs, split by paper not by
> question, versioned by content hash, written as JSONL with a manifest
> recording seed, generator version and counts. Generate 50k pairs. Then measure
> the FuzzyDecoder on the test split and write that number into NOTES.md as the
> baseline to beat. Show me 10 sample heavy-paraphrase pairs before generating
> the full set.

---

### [ ] M9 — Neural slot decoder

**Build:** `decode/neural.py` implementing `SlotDecoder` with a fine-tuned
encoder (DeBERTa-v3-small or MiniLM) that, given a leaked chunk and a candidate
question, predicts the symbol of each slot plus a calibrated confidence.
`ml/train_decoder.py` with a config file, run cards, early stopping, and
checkpoint export to `models/<version>/`.

**Acceptance:** on the M8 test split, `NeuralDecoder` beats `FuzzyDecoder` by a
clear margin under medium and heavy paraphrase, with the comparison in one
table. Confidence is calibrated (reliability plot, expected calibration error
reported) because the scorer consumes it as a probability. Contract tests shared
with `FuzzyDecoder` all pass.

**Prompt:**
> Read CLAUDE.md. Build M9: the neural slot decoder. Define the SlotDecoder
> protocol and make FuzzyDecoder satisfy it, with contract tests both
> implementations must pass. Implement NeuralDecoder in examfp/decode/neural.py:
> fine-tuned DeBERTa-v3-small scoring (leaked chunk, candidate question, slot)
> to a symbol distribution, returning calibrated confidences. Training lives in
> ml/train_decoder.py with a YAML config, run cards written per run, early
> stopping and checkpoint export to models/<version>/. Evaluate against
> FuzzyDecoder on the M8 test split, per paraphrase strength, in one table, and
> report expected calibration error. The service must select the decoder by
> config, not by code change.

---

### [ ] M10 — Adversarial training loop

**Build:** `ml/adversarial.py` — iterate: generate attacks, find the decoder's
failures, retrain on them, re-attack. Hold out a frozen final test set never
seen by any loop iteration.

**Acceptance:** identification accuracy under heavy paraphrase improves across
at least three rounds, measured on the frozen test set, and the curve is
plotted. The adversary's success rate falls. No regression on the clean and
retyped settings.

**Prompt:**
> Read CLAUDE.md. Build M10: adversarial training. ml/adversarial.py runs rounds
> of: adversary generates paraphrase attacks -> NeuralDecoder attempts recovery
> -> failures are collected -> decoder retrains on them -> adversary attacks the
> new decoder. Keep a frozen final test set that no round ever trains or
> validates on. Run at least three rounds. Produce a figure of accuracy per round
> on the frozen set, and assert no regression on clean and retyped inputs.
> Everything seeded and reproducible from the run cards.

---

### [ ] M11 — Full evaluation harness

**Build:** `eval/` sweeps across six attack classes (crop, OCR noise, retype,
paraphrase at three strengths, translation round-trip, collusion 2–5 centres) ×
decoder (fuzzy, neural, adversarial) × k leaked questions. Figures for the
report and paper. Also a **tolerance × read floor × false-identification sweep
across noise regimes** (clean, retype, OCR noise, each paraphrase strength):
for each reader's measured misread rate, the tolerance it implies, the floor
that keeps innocent identifications at zero, and what that floor costs
single-source identification. Include the bits-based floor (NOTES.md, M5.5)
with enough trials to stabilise its threshold.

**Acceptance:** `.\tasks.ps1 bench` writes `eval/out/results.csv` plus figures;
false-identification rate reported for every cell and is zero or has a stated
bound; the empirical Tardos constant `k` is measured and written into the
capacity report, replacing `<unset>`.

**Prompt:**
> Read CLAUDE.md and NOTES.md. Build M11: the full evaluation harness. Sweep six
> attack classes (crop, OCR noise, retype, paraphrase light/medium/heavy,
> Hindi round-trip translation, collusion of 2–5 centres) against three decoders
> (fuzzy, neural, adversarially trained) over k = 1..12 leaked questions, 200
> trials per cell, all seeded. Write eval/out/results.csv and generate the
> figures: accuracy vs k per attack, decoder comparison per paraphrase strength,
> adversarial rounds, and false-identification rate per cell. Then measure the
> empirical Tardos constant k from the collusion experiments and wire it into
> Paper.capacity_report, replacing the <unset> placeholder, clearly labelled
> measured rather than proved.

---

## Phase 3 — Make it deployable (Mar 2027)

### [ ] M12 — Service layer

**Build:** `service/` FastAPI app — routers for exams, papers, traces, health;
Postgres with Alembic migrations; Celery or RQ worker with Redis for paper
generation and tracing jobs; JWT auth with the `authority` and `investigator`
roles; envelope encryption via a `Vault` interface (env-var implementation for
dev, pluggable for prod); append-only audit log; structured JSON logging with
request ids; Prometheus metrics; `/healthz` and `/readyz`.

**Acceptance:** `pytest tests/service` covers the happy path and the role
boundary (an investigator token cannot read codebook contents — assert 403);
generating 1,000 papers runs as a background job with progress; every trace
writes an audit row containing model and codebook version; OpenAPI docs
generated.

**Prompt:**
> Read CLAUDE.md. Build M12: the service layer in service/. FastAPI with routers
> for exams, papers, traces and health; SQLAlchemy models and Alembic migrations
> for Postgres; a Redis-backed worker for paper generation and tracing with job
> status endpoints; JWT auth with roles authority and investigator; a Vault
> protocol for KEK access with an env-var dev implementation; envelope encryption
> of codebooks at rest; an append-only audit table recording actor, time, input
> hash, model version, codebook version and outcome; structured JSON logs with
> request ids; Prometheus metrics; /healthz and /readyz. The service imports
> examfp but never ml. Tests must include a role-boundary test asserting that an
> investigator token receives 403 when attempting to read codebook contents.

---

### [ ] M13 — Dashboard

**Build:** `web/` React + TypeScript + Tailwind — four screens: create exam
(upload master paper), review and approve variants with the fairness report
inline, generate papers with job progress, trace a leak with the verdict,
evidence slots and a downloadable PDF report.

**Acceptance:** Playwright end-to-end test drives upload → approve → generate →
trace → download against the running stack and asserts the correct centre
appears. Dashboard never displays raw codewords.

**Prompt:**
> Read CLAUDE.md. Build M13: the dashboard in web/ with React, TypeScript,
> Vite and Tailwind. Four screens: create exam, review and approve variants with
> the fairness report shown per variant, generate papers with live job progress,
> and trace a leak showing outcome, margin, threshold, positions read versus
> erased, ranked centres and a download link for the evidence PDF. Raw codewords
> must never be rendered. Add a Playwright end-to-end test that drives the whole
> flow against the compose stack and asserts the correct centre is named.

---

### [ ] M14 — Deployment and runbook

**Build:** `deploy/` — multi-stage Dockerfiles for api, worker and web;
`docker-compose.yml` for the full stack; Caddy reverse proxy with TLS;
`.env.example`; CI building and pushing images on tag; `docs/RUNBOOK.md`
(deploy, roll back, rotate keys, restore from backup, what to do when a trace
is disputed); `docs/THREAT_MODEL.md`; backup job for Postgres with a documented
restore drill; `.\tasks.ps1 smoke` hitting a deployed instance.

**Acceptance:** `docker compose up` from a clean machine brings the whole stack
up; the smoke test passes; the restore drill is performed once and its result
recorded in the runbook; a load test shows trace latency at p95 under one
second with 1,000 centres.

**Prompt:**
> Read CLAUDE.md. Build M14: deployment. Multi-stage Dockerfiles for api, worker
> and web; docker-compose.yml wiring api, worker, postgres, redis, web and a
> Caddy reverse proxy with TLS; .env.example documenting every variable; a CI
> workflow building and pushing images on tag; docs/RUNBOOK.md covering deploy,
> rollback, key rotation, backup and restore, and the procedure when a trace
> result is disputed; docs/THREAT_MODEL.md listing assets, actors, attacks and
> mitigations; a nightly Postgres backup job; and tasks.ps1 smoke running a
> post-deploy smoke test. Acceptance: docker compose up from a clean machine,
> smoke test green, and a documented restore drill.

---

## Phase 4 — Make it count (Apr–May 2027)

- [ ] **M15** Provisional patent filing through the college IP cell — **before**
      the paper is submitted anywhere. Publication destroys patentability.
- [ ] **M16** Paper draft from NOTES.md, the figures from M11 and the capacity
      finding from M2.
- [ ] **M17** Phase II report and viva demo script.

---

## Schedule

| Period | Milestones |
|---|---|
| Oct 2026 | M4, M5, M6 |
| Nov 2026 | M7, M8 |
| Dec 2026 | M9 + **Phase I review** |
| Jan 2027 | M10 |
| Feb 2027 | M11 |
| Mar 2027 | M12, M13 |
| Apr 2027 | M14, M15 |
| May 2027 | M16, M17 + **Phase II review** |

## Cut lines if behind schedule

Cut in this order: M13 dashboard (CLI demos fine) → M7 OCR → translation
attacks in M11 → M14 reduced to a single Dockerfile and a runbook.

**Never cut:** M5 (removes the known weakness), M9 (the title's claim), M11
(the evidence). Without those three the project is not what its title says.
