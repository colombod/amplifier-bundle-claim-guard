# Acceptance Evaluation — Methodology

This document describes **how claim-guard was accepted**: the methodology for proving the gate
catches real, known-good defects — at a level another engineer can reproduce on their own PR.

It deliberately contains **no raw run output, no absolute machine paths, and no provider data**.
The gate is non-deterministic at the LLM layer (the deterministic part is only the `claim_ledger`
aggregation + gate rule), so the artifact that matters is the **methodology and the pass/fail
bar**, not a transcript. Raw runs live outside the repo (see *Where the runs live*) and are not
committed.

---

## 1. The acceptance question

> Given a real change that a human reviewer later found serious blockers in, does the gate —
> run against the **pre-remediation** state of that change — independently flag those same
> blockers as **REFUTED** (blocking), with `file:line` evidence? And as a **control**, do those
> same claims flip to **CONFIRMED** when the gate is run against the **fixed** head?

This is a two-sided test on purpose. Catching the blockers on the adverse state shows the gate has
**power** (it finds real defects). The control on the fixed head shows it has **specificity** (it
isn't just always shouting BLOCK) — the same claims must pass once the code actually keeps its
promise.

## 2. The evaluation subject

Any merged PR that (a) shipped real correctness/safety work and (b) had **known blockers** found
after the fact — by a human reviewer, an incident, or a follow-up fix — is a usable subject. The
follow-up fixes are the answer key: each remediation commit corresponds to a blocker the gate
should have caught on the pre-fix state.

The acceptance run used a context-intelligence server PR with **four** documented blockers
(referred to as B-1…B-4), each later fixed by a specific commit. Summarised generically:

| Blocker | Class | Shape |
|---|---|---|
| B-1 | safety / integrity | a change that made a failure *survivable* but not *safe* — degraded operation could still corrupt data because no write path consulted the health signal |
| B-2 | concurrency | a guard applied "one branch over" — present on a rare path, absent on the common retry path that reaches the same chokepoint |
| B-3 | boundary / quantitative | a cap with no lower-bound validator — a negative value inverted it |
| B-4 | test-correspondence | tests that certified *liveness* while the commit claimed *integrity* — green for the wrong reason |

## 3. Reconstructing the adverse ("pre-remediation") state

The core trick: build the exact tree the reviewer saw, **before** any blocker was fixed, so the
answer key (the remediation commits) is **excluded** from what the gate sees.

1. Identify three revisions:
   - `BASE` — the merge-base with the target branch;
   - `ADVERSE_HEAD` — the last commit **before** any B-1…B-4 remediation (all blockers present);
   - `FIXED_HEAD` — a head **after** the remediations (the control).
2. **Verify the boundary.** Confirm each blocker is actually present at `ADVERSE_HEAD` and actually
   fixed at `FIXED_HEAD`, by inspecting the load-bearing line. (E.g. a cap field with vs without its
   lower-bound validator.) This step is easy to get wrong — a head chosen one commit too late may
   already contain a fix and silently leak the answer.
3. **Exclude the remediation commits** from the changeset range. The gate is fed `BASE..ADVERSE_HEAD`
   only — never the range that contains the fixes or their commit messages (those messages would
   hand the gate the answer).

## 4. Inputs fed to the gate

Scope everything to `BASE..ADVERSE_HEAD`:

| Input | What it is | How to produce it (generic) |
|---|---|---|
| worktree | a detached checkout of the shipped source **at `ADVERSE_HEAD`** — the code actually under review | `git worktree add <worktree_dir> <ADVERSE_HEAD>` |
| diff | the changeset under review | `git diff <BASE>..<ADVERSE_HEAD> > <diff_file>` |
| commit messages | a primary claim source (NO remediation messages) | `git log <BASE>..<ADVERSE_HEAD> > <commits_file>` |

Optionally, a prior **design-council verdict** for the change can be fed in as an extra claim
source (each addressed `FAIL`/`CONCERN` becomes a claim to verify against the shipped code).

## 5. Running the gate

Point the gate at the worktree as the `repo_path`, with the diff and commit messages as the claim
sources, under `gate_policy: blocking-with-waiver`. Either drive it via the `/claim-guard` concierge
skill, or run the `verify-claims` recipe (full install), or — under the lightweight `--app` install
— ask the session to orchestrate the lenses and aggregate via `claim_ledger` (see the README
*Usage* section). All `file:line` anchors resolve into the worktree.

Repeat the run a few times (the acceptance used several independent repetitions) — the LLM layer is
non-deterministic, so the bar must be met **reliably**, not once.

## 6. The pass/fail bar

**Adverse run (power):**
- The gate returns **BLOCK**.
- Each of B-1…B-4 appears as a **REFUTED** (or otherwise blocking) claim, with a `file:line` anchor
  into the worktree and a counter-case.
- Coverage is complete (no INDETERMINATE from missing lenses / empty harvest) — a BLOCK that is
  actually an incomplete run does **not** count as a pass.

**Control run (specificity):**
- Run the same gate against `FIXED_HEAD` (a worktree at the fixed head; diff/commits scoped to
  include the fixes).
- The claims corresponding to B-1…B-4 flip to **CONFIRMED** (each now carrying the `file:line` of
  the code that keeps the promise). Claims that remain genuinely untestable statically may stay
  `UNTESTABLE` — that is honest, not a failure — but the fixed defects must no longer read REFUTED.

The acceptance is met when the adverse run **reliably** catches all four blockers and the control
run **reliably** clears the fixed ones. (Extra REFUTED claims beyond B-1…B-4 are expected and
welcome — a sharper gate finds more than the human did; they are reported, not penalised.)

## 7. Interpreting the result honestly

- **The deterministic core is the verdict, not the finding.** `claim_ledger` computes worst-wins
  aggregation and the BLOCK/PASS/INDETERMINATE rule mechanically; the *findings* come from the LLM
  lenses and vary run to run. Judge the gate on whether the **blocking findings reliably appear**,
  not on byte-identical output.
- **A BLOCK on the adverse state is only meaningful with the control.** Without the fixed-head
  control, a gate that always blocks would "pass" trivially. The flip-to-CONFIRMED is what proves
  the gate discriminates.
- **Evidence is the currency.** A REFUTED without a `file:line` anchor and a counter-case does not
  count — the ledger rejects unanchored CONFIRMED/REFUTED verdicts, and the acceptance holds the
  human to the same bar when reading the matrix.

## 8. Phase 2 validation (DTU)

**Rule: bundles are validated in a Digital Twin Universe, never by a local host install.** The
dynamic bench pulls in a Digital-Twin dependency surface (parallax-discovery, digital-twin-universe,
amplifier-tester) and the `pen-tester` stands real adverse states up inside a twin — so validation
runs where the bundle would actually run, not against the developer's host, and leaves the host
untouched.

### 8.1 What was validated in the twin (compose / parse / tool round-trip)

Four checks, all at the **composition and interface** level — proving the Phase-2 surface loads,
parses, and that the ledger's Phase-2 ops round-trip. **Result: 4/4 PASS.**

| # | Check | What it proves |
|---|---|---|
| 1 | **Root bundle composes** (`bundle.md`) | the 6 static lenses + the `claim_ledger` tool activate from the `@main` git source with **no module-activation failure** — the static gate is intact and installable as shipped |
| 2 | **Phase-2 standalone composes** (`bundles/with-probing.yaml`) | the 3 Phase-2 agents (`probe-designer`, `pen-tester`, `regression-graduator`) resolve, and the parallax-discovery / digital-twin-universe / amplifier-tester dependency bench resolves alongside them |
| 3 | **Both recipes parse** (`verify-claims`, `probe-claims`) | the static and dynamic pipelines are well-formed and loadable |
| 4 | **`claim_ledger` round-trips** | `add_claim → list_claims → aggregate` works end-to-end, with the `probed` / `deferred` coverage fields live (i.e. the Phase-2 `record_probe` / `defer_claim` / `graduate_test` ops are wired and the coverage counters they feed are populated) |

This is a **composition/interface** acceptance, not a behavioural one. It establishes that Phase 2
is loadable, parseable, and that its ledger seam works — the prerequisites for a behavioural run.

### 8.2 The remaining follow-up (a full behavioural pen-test in a twin — not yet done)

Running the **full behavioural loop** — `probe-designer` designs the experiment, `pen-tester` stands
the adverse state up in the twin and attacks it, `regression-graduator` graduates a surviving probe
into a standing test — has **not** been exercised end-to-end on a real target. It is the documented
next exercise, not a completed claim. It requires, inside the twin:

- a **reachable LLM provider** (so the agents can actually run);
- **nested Incus/Docker** (so the pen-tester can build the adverse states the probes call for);
- a **target changeset** plus a completed **`verify-claims` ledger** present (the `run_id` seam
  `probe-claims` consumes);
- a **probe budget** set (the DTU-spend cap on how many probes actually run).

Until that run is done, treat Phase 2 as **built and composition/interface-validated**, with the
behavioural loop as its intended-but-unexercised use. See `KNOWN_ISSUES.md` (KI-2).

## 9. Harvest stability (KI-1)

This section is the **acceptance measurement for KI-1** — harvester non-determinism. It is separate
from the blocker-catch acceptance above (§1–§7, which measures *power* and *specificity*); this one
measures **reproducibility of the claim set** run-to-run.

### 9.1 What KI-1 was

On repeated harvest runs against the **same** changeset, the two harvester agents produced
**different claim counts** — observed **18 / 77 / 22 / 11** across four runs — because the change was
decomposed into a different number of claims each run (**granularity** variance) and each claim was
worded differently (**phrasing** variance). Phrasing variance is the worse of the two: the ledger's
stable `claim_id` (design finding F-9) is a hash of normalized claim text + type + source, so a
reworded restatement of the *same* claim hashes to a *different* id, defeating run-to-run matrix
diffing. The top-line verdict and the B-1…B-4 catch stayed stable throughout; only the detailed
matrix was non-reproducible. See `KNOWN_ISSUES.md` (KI-1).

### 9.2 The two-part fix (what the metric measures)

- **Code-level (`modules/tool-claim-ledger/.../identity.py`):** hardened `normalize_text` into a
  canonical form (NFKC, code/prose segmentation with code-token preservation, casefold, a closed
  contraction map, punctuation→space, a small closed filler set with a NEVER-STRIP guard for
  negation/quantifiers/modals/numbers). It collapses trivial rewordings to one id **without**
  over-collapsing distinct claims — proven by the identity unit suite (idempotence, reword-stable,
  type-sensitive, and the R-1 minimal-pairs *distinct-claims-stay-distinct* tripwire).
- **Prompt-level (both harvester agents + the shared `claim-harvesting` skill):** a single shared
  **claim contract** — the atomicity rule (one load-bearing assertion per claim; split/merge
  criteria; claim count = distinct mechanism × distinct forbidden-property) and a **canonical
  claim-statement form** (subject–predicate, present tense, symbol-named, controlled vocabulary) that
  the agents emit and the normalizer expects. Co-designed so they cannot drift.
- **Determinism knob:** `temperature: 0` pinned on the two harvest steps of `verify-claims.yaml`
  (intended as a variance *reducer*, never a guarantee). **Measured to be INERT on the shipped
  stack** — see §9.4: the harvest routes to Claude Opus ≥ 4.7, and the anthropic provider does not
  send a `temperature` for Opus ≥ 4.7 (it is silently ignored). So on any Opus-4.7+/Sonnet-5
  deployment this prong does nothing, and **only the prompt prong is actually active.** The pin is
  left in place because it is correct for a sampling-capable model, but it delivers no determinism on
  the current routing.

### 9.3 The metric + how to run it

The harness is committed at **`scripts/harvest_stability.py`**. It does **not** run the harvesters
itself (that is an LLM step, run in a DTU per §8's never-install-locally rule); it **consumes the
`ledger.json` files** those repeat runs produced and scores their agreement. It **imports the real
`identity.py`**, so its `claim_id`s match the ledger exactly — which means it also detects
**prompt↔normalizer drift** (spec risk R-6): if the agents drift from the canonical form the
normalizer expects, id-stability drops here.

It reports three metrics plus one hard guardrail:

- **Jaccard@claim_id** — mean pairwise `|A∩B| / |A∪B|` over the runs' claim-id sets. Isolates the
  **prompt** fix (granularity + phrasing): how much the claim *sets* overlap run-to-run.
- **claim_id stability** — of the claim observations that recur across runs, the fraction that belong
  to ids recurring across runs. Isolates the **code** fix (normalization): a recurring claim that
  still forks its id is a normalization miss.
- **count dispersion** — median claim count and spread (the headline symptom, 18/77/22/11).
- **B-1…B-4 caught-every-run guardrail** — the four incident blockers must be present in **every**
  run; a determinism gain that dropped a blocker would fail here (guards spec R-3 / F-1).

**Invocation (generic paths; run against N≥5 ledgers from repeat harvests on ONE changeset):**

```bash
# Score N ledger.json files (defaults: --min-jaccard 0.9 --min-id-stability 0.9):
python scripts/harvest_stability.py <run1>/ledger.json <run2>/ledger.json ... \
    [--min-jaccard 0.9] [--min-id-stability 0.9] \
    [--require-blocker B-1 --require-blocker B-2 ...] [--json]

# Self-check the metric itself on synthetic claim sets (no ledgers needed):
python scripts/harvest_stability.py --selftest
```

Exit code is **0 iff every threshold and the blocker guardrail are met**, 1 otherwise — suitable for
wiring into the acceptance methodology. Keep the input `ledger.json` files under the uncommitted
`.amplifier/evaluation/…` tree (§10); commit only the harness and a results **summary**.

### 9.4 Live result (measured) — the fix does NOT meet the bar on the shipped stack

The N≥5 in-twin harvest run has now been done, and the result is a **negative**: the shipped
configuration **FAILS** the KI-1 acceptance bar. Recording it honestly.

**Setup.** N=5 repeat harvests on ONE fixed changeset (the fixed PR#70 `c324cbe` changeset), run
in a Digital Twin, bundle `@b646bf2`, scored by `scripts/harvest_stability.py` and independently
re-scored on host. The numbers below are real measurements, not projections.

| Config | Jaccard@claim_id (mean pairwise) | claim_id stability | claim counts | Bar 0.9 / 0.9 |
|---|---|---|---|---|
| **SHIPPED** (`verify-claims`, `temperature: 0` in `agent_config`) | **0.0075** | **0.0395** | 54 / 58 / 75 / 82 / 85 | **FAIL** |
| bare path (no temperature pin) | 0.0 | 0.0 | 58–101 | FAIL |

Both paths agree: the claim-id sets are **essentially disjoint run-to-run.** The shipped config is a
hair above zero, not near the 0.9 target.

**Root cause #1 — the temperature prong is INERT on this stack (code-proven).** The harvest routes
to Claude Opus ≥ 4.7 (opus-4-8 / opus-5), and the anthropic provider **does not send a `temperature`
for Opus ≥ 4.7** — it is silently ignored ("Opus 4.7+ silently ignores temperature"). So on any
Opus-4.7+/Sonnet-5 deployment the `temperature: 0` pin does **nothing**; **only the prompt prong is
actually active.** The near-identical scores of the shipped vs. bare paths above are the empirical
confirmation of this: pinning temperature changed nothing because the pin never reached the model.

**Root cause #2 — the dominant residual variance is paraphrase + granularity**, which
`identity.py` **deliberately does not collapse.** The canonical normalizer omits stemming and
synonym-folding on purpose (to avoid the R-1 false-merge risk — merging genuinely distinct claims is
worse than failing to merge paraphrases). The prompt prong (canonical claim-statement form +
atomicity rule) is the only thing pushing toward convergence, and **the prompt prong alone does not
force it**: the agents still paraphrase the same claim differently and decompose the change at
different granularities run-to-run, so the normalized text differs and the `claim_id`s fork.

**What this does and does not invalidate.**
- The **code prong is still correct and proven** — it collapses *trivial* rewording (case, unicode,
  punctuation, articles, contractions, identifier-case) as designed; the 118-test suite and the R-1
  minimal-pairs tripwire all pass. It simply does not, by itself, collapse *paraphrase*, which is the
  variance that actually dominates here.
- The **R-6 drift guard is in place** (13 dedicated tests) and the harness (importing the real
  `identity.py`) would catch prompt↔normalizer drift.
- But **end-to-end run-to-run reproducibility is NOT achieved on the shipped stack.** The 0.9 / 0.9
  bar is not met. KI-1 is **not empirically confirmed** — it is an **open issue** (see
  `KNOWN_ISSUES.md` KI-1, tracked as `claim_gate-ryw`).

### 9.5 Status — what is proven vs. what is open

**Proven (deterministic, unit-level):**
- the `identity.py` canonical-form invariants, including the R-1 over-collapse minimal-pairs
  tripwire — the full module suite (**118 tests**) passes; the R-6 drift guard (**13 tests**) is in
  place;
- the harness's own correctness — `--selftest` passes;
- the harness **correctly scores the pre-fix baseline as FAIL** (mean pairwise Jaccard@claim_id 0.0,
  claim_id stability 0.0, count 11–77) — i.e. the metric is sensitive to exactly the failure KI-1
  describes.

**Open (empirical — measured, and NOT met):** the live N=5 in-twin run scored the **shipped config
at Jaccard 0.0075 / id-stability 0.0395**, far below the 0.9 / 0.9 bar (§9.4). The two-prong fix as
shipped does not deliver run-to-run reproducibility on an Opus-4.7+/Sonnet-5 stack, primarily
because the temperature prong is inert there and the prompt prong alone does not force paraphrase +
granularity convergence. **KI-1 remains open**, tracked as follow-up `claim_gate-ryw`; the path
forward is a design decision documented in `KNOWN_ISSUES.md` (KI-1).

## 10. Where the runs live (and what is never committed)

Raw evaluation artifacts — worktrees, diffs, ledgers, matrices, and per-run logs — live **outside
this repo**, under a workspace-local `.amplifier/evaluation/claim-guard/` tree, and are **not
committed**. They contain full run transcripts and machine-specific paths; keeping them out of the
repo is deliberate.

**Committed:** this methodology document only.
**Never committed:** raw run output (`run.jsonl`/logs), the reconstructed worktrees, per-run
ledgers/matrices, absolute machine paths, and any provider/model or credential data.

To reproduce, recreate the `BASE / ADVERSE_HEAD / FIXED_HEAD` reconstruction on your own subject
PR per §3–§6 and keep your runs in an untracked location.
