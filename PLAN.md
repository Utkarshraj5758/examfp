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
outcome `MULTI_SOURCE_SUSPECTED` (whenever the gate empties above the floor; it
names nobody and lists three possible causes); the unique-pair hypothesis
demoted to an opt-in `trace --hypotheses`, printed with its measured accuracy
(98/109); `collude()` attack (2–5 centres, minority strategy); calibration,
floor, bits-floor and collusion rows in `eval/bench.py`; claims corrected;
ADR 0003.

**Status:** done (branch `m5.5-consistency-gate`). 0 innocents identified for
coalitions of 1–5 after the change; single-source 6-question leaks unchanged at
200/200; multi-source flagged on 800/800 colluded leaks and 0/200 single-source.
Cost: leaks of 1–2 questions no longer name a centre. For 2 questions that is a
capacity bound (17.79 bits available vs ≥ 18.59 needed), not a tuning gap. The
pair was taken out of the verdict because all 11 wrong pairs came from 3–5-centre
leaks, which the observation cannot tell apart from 2-centre leaks. Numbers in
NOTES.md, M5.5.

---

### [~] M6 — Fairness checker

The claim the whole project rests on, made machine-checkable.

**Build:** `examfp/fairness/`: `answers.py` (SymPy, exact `Rational`),
`bands.py` (wraps the existing band validator in `models.py`, which stays
frozen, and adds the step rule), `nli.py` (`cross-encoder/nli-deberta-v3-small`,
bidirectional entailment above a configurable threshold, loaded lazily and
cached), `readability.py` (word, syllable and rare-word counts within
tolerance). Each check returns `(passed, reason)`. One `FairnessReport` per
variant with per-check pass/fail and reason.

**Owner decisions (2026-10-17, planning session) — binding:**

1. **Three channels, three tests, never mixed; the tests assert the separation.**
   - *Wording* (wording and unit-form slots): numbers must be identical to the
     reference, then NLI entailment both ways, then readability. Never SymPy.
   - *Numeric* (banded groups): SymPy answer equivalence. **Never passed to the
     NLI model**, which would reject valid variants as non-equivalent statements.
   - *Difficulty band*: arithmetic rules only (digit counts, trivial operands,
     step count).
   - Option orders: structural check (same options, same correct text).
   - A spy NLI backend must prove that no numeric variant, and no pair whose
     numbers differ, ever reaches the model.
2. **Step count, recorded in a new ADR 0004.** Use the canonical written method:
   partial products for multiplication; for a percentage, one step when it is
   a clean fraction of 100, two otherwise. The ADR states the definition, why
   it was chosen, and the limitation that students may solve by other methods.
   It is expected to reject the sample paper's q3 (32 × 45), q7 (45 × 32) and
   q4 (20%, 25% against the reference 15%) variants; that is correct behaviour.
   **Open, ask the owner before adopting:**
   - Division has no rule yet (bands q1, q6). Proposal: one step per quotient
     digit in short division, which is constant when the answer is fixed.
   - Read "clean fraction" as 100/p being an integer (20%, 25%: one step; 40%
     = 2/5: two steps). Confirm that reading.
   - `add` and `subtract` bands have no rule either; they must fail closed.
3. **Fix `data/papers/sample.json` so it passes every check.** Then re-run
   `.\tasks.ps1 bench` and report which published numbers moved.
   - Do not assume the durable-bit percentage or the k-sweep are unchanged.
     Alphabets shrink, which changes the bit counts and possibly the RS
     packing (ADR 0002).
   - Check the M5.5 calibration too. The guard test pins the pair accuracy at
     98/109, and the read floor and bits floor may move. Follow ADR 0003's
     recalibration procedure if they do.
   - For q4, a fix can keep 7 variants: 12% of 500 and 48% of 125 are
     two-step, like 15%.
4. **NLI stays strict, with no exemptions for context slots.** Replace the
   place-name intro swaps (q1 Nashik / Pune highway, q6 Bengaluru lab / school
   lab, q7 Delhi bookshop / Chennai store) with same-place paraphrases, two per
   slot.
   - F14 stays labelled fair. If the model rejects it, that is a false
     rejection against the budget of two.
   - **Fixture labels are never revised to match model output.** Add this
     principle to CLAUDE.md, under ML discipline.
5. **Dependencies.** Downloads were approved in the planning session;
   reconfirm at the session kickoff.
   - SymPy 1.14.0 becomes a base dependency.
   - A new `fairness` extra, separate from `ml`: torch 2.14.1, transformers
     5.19.0, tokenizers 0.23.3, sentencepiece 0.2.2 and wordfreq 3.1.1
     (rare words).
   - The model `cross-encoder/nli-deberta-v3-small` is pinned at revision
     `fa2804872c3b4bd748f38c0185cc85775361e735`. Fetch only
     `model.safetensors` and the tokenizer and config files, not the ONNX
     copies. At runtime, load local files only.
6. **The acceptance test is marked and local-only.** CI skips it; the
   fake-model separation tests run in CI. Record its result in NOTES.md with
   the model revision and date, so drift shows up in the diff. M14 caches the
   model in CI.
7. **Model reliability, M9's baseline.**
   - Build a wording set of about 60 pairs outside the 40-entry fixture: half
     equivalent, half not. The non-equivalent half covers a changed quantity
     asked for, changed units, an added or removed constraint, and a reversed
     relationship.
   - Report the NLI model's accuracy on it with a confidence interval in
     NOTES.md.
   - Also report its agreement with the hand labels on the fixture's wording
     subset.

**Fixture (approved):** `tests/fixtures/variants.json`, 40 entries: 29 fair,
11 unfair (2 `wrong_answer`, 2 `extra_step`, 2 `trivial_operand`, 2
`digit_jump`, 3 `changes_question`). Each unfair entry fails exactly the rule on
its label. After the sample-paper fix, update the `approved` flags.

**Acceptance:** at most 2 false rejections on the 29 fair entries and zero false
acceptances on the 11 unfair. The NLI model loads lazily and scores a pair in
under 300 ms on CPU.

**Prompt:**
> Read CLAUDE.md and PLAN.md's M6 section, including the owner decisions. Build
> M6, the fairness checker. Downloads are approved: the packages listed in M6
> plus cross-encoder/nli-deberta-v3-small at revision fa28048. Before adopting
> the step rule, ask the owner the open questions in decision 2.

**Status (2026-10-17, branch `m6-fairness`): built; acceptance not met, recorded
on the owner's decision.** Everything in the Build list exists, plus a unit-form
channel (`units.py`).

- *Decision 2 answered:* the step rule (ADR 0004) covers division (dividend
  digits, non-zero remainders), addition and subtraction (columns, carries or
  borrows), and percentages (one step when 100 / p is whole). Every carry counts,
  and the multiplier is the second operand in fill order.
- *Owner rulings after the first run:* unit forms are judged by a unit table,
  not NLI (the tokenizer reads ² and ³ as `[UNK]`); the model and threshold 0.5
  stay; record the result and fix the paper.
- *Acceptance:* 0 false acceptances on the 11 unfair entries, each failing
  exactly its labelled rule. **3 false rejections** on the 29 fair (F11, F13, F14,
  all NLI) **against a budget of 2.** Lazy load works, at 76 ms per pair; the
  sample paper passes every check. The budget test is a strict xfail; the
  rejection set is pinned.
- *Decision 3:* sample.json is fixed (q3 and q7 now 5 variants, q4 7) and
  re-benched. The ADR 0003 procedure leaves the calibration unchanged (0
  misreads; floor 11; 0 innocents for coalitions of 1–5). The pair accuracy
  moved, 98/109 → 117/126. 3-question leaks: 82% → 80%.
- *Decision 7:* held-out 55/60 (95% CI 81.6–97.2%), with 2 false acceptances
  (changed quantity); fixture agreement 17/20.

- *Stronger model, tried (2026-10-17):* `cross-encoder/nli-deberta-v3-base@6c749ce`,
  owner-approved and pinned beside the small model, scored 54/60 on the held-out
  set (2 false acceptances, 4 false rejections) against small's 55/60. Under the
  rule fixed before scoring, small stays. The one fixture run, with small, is
  unchanged: 3 false rejections.

Numbers, findings and open items are in NOTES.md, M6. **To close M6:** meet
the false-rejection budget without tuning on the fixture, for example with a
stronger pinned model chosen on held-out data (the M9 baseline above).

---

### [ ] M7 — OCR path

**First task, before the OCR acceptance test runs:** measure the OCR reader's
per-slot misread rate and recalibrate the decision rule against it —
`MISREAD_RATE`, hence the gate tolerance, then `MIN_READ_SLOTS` — using the
procedure in ADR 0003. *Why first:* the gate's tolerance is 0, calibrated for the
fuzzy text reader (0 misreads in 104,026 reads; 104,098 after M6). At tolerance 0, a 1% per-slot
misread rate makes 1 − 0.99¹¹ ≈ 10% of genuine 11-slot leaks fail the gate, and
those leaks would come back `MULTI_SOURCE_SUSPECTED` or `INSUFFICIENT`. That
would look like an OCR failure when it is really a gate calibrated for the wrong
reader. While in this code, decide on the proposed rename of
`MULTI_SOURCE_SUSPECTED` (NOTES.md, M5.5): the outcome has three causes, and
OCR misreads make the second more likely.

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
with enough trials to stabilise its threshold. **Hypothesis to validate
(single seed, M5.5):** the `--hypotheses` pair never included an outsider at
24 or more slots read. All 75 outsider pairs in the seed-1 floor sweep came
from leaks with 11–23 reads. Sweep pair accuracy against slots read across
many seeds before anyone relies on it.

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
restore drill; `.\tasks.ps1 smoke` hitting a deployed instance. **Also (from
M6):** cache the NLI model (`cross-encoder/nli-deberta-v3-small` at revision
`fa28048`) in CI, so the local-only fairness acceptance test runs there too.

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
