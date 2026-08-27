# Acceptance Evaluation — Methodology

This document describes **how claim-guard was accepted**: the methodology for proving the gate
catches real, known-good defects — at a level another engineer can reproduce on their own PR.

It deliberately contains **no raw run output, no machine-specific paths, and no provider data**. The
gate is non-deterministic at the LLM layer (the deterministic part is only the `claim_ledger`
aggregation + gate rule), so the artifact that matters is the **methodology and the pass/fail bar**,
not a transcript. Raw runs live outside the repo (see §9) and are not committed.

---

## 1. The acceptance question

> Given a real change that a human reviewer later found serious blockers in, does the gate — run
> against the **pre-remediation** state of that change — independently flag those same blockers as
> **REFUTED** (blocking), with `file:line` evidence? And as a **control**, do those same claims flip
> to **CONFIRMED** when the gate is run against the **fixed** head?

This is a two-sided test on purpose. Catching the blockers on the adverse state shows the gate has
**power** (it finds real defects). The control on the fixed head shows it has **specificity** (it
isn't just always shouting BLOCK) — the same claims must pass once the code actually keeps its
promise.

## 2. The evaluation subject

Any merged PR that (a) shipped real correctness/safety work and (b) had **known blockers** found
after the fact — by a human reviewer, an incident, or a follow-up fix — is a usable subject. The
follow-up fixes are the answer key: each remediation commit corresponds to a blocker the gate should
have caught on the pre-fix state.

The acceptance run used a real server PR with **four** documented blockers — named below by their
shape, and referred to by those names throughout — each later fixed by a specific commit:

| Blocker | Class | Shape |
|---|---|---|
| **degraded-boot integrity** | safety / integrity | a change that made a failure *survivable* but not *safe* — degraded operation could still corrupt data because no write path consulted the health signal |
| **one-branch-over guard** | concurrency | a guard applied "one branch over" — present on a rare path, absent on the common retry path that reaches the same chokepoint |
| **cap inversion** | boundary / quantitative | a cap with no lower-bound validator — a negative value inverted it |
| **wrong-thing tests** | test-correspondence | tests that certified *liveness* while the commit claimed *integrity* — green for the wrong reason |

## 3. Reconstructing the adverse ("pre-remediation") state

The core trick: build the exact tree the reviewer saw, **before** any blocker was fixed, so the
answer key (the remediation commits) is **excluded** from what the gate sees.

1. Identify three revisions:
   - `BASE` — the merge-base with the target branch;
   - `ADVERSE_HEAD` — the last commit **before** any blocker remediation (all four present);
   - `FIXED_HEAD` — a head **after** the remediations (the control).
2. **Verify the boundary.** Confirm each blocker is actually present at `ADVERSE_HEAD` and actually
   fixed at `FIXED_HEAD`, by inspecting the load-bearing line. (E.g. a cap field with vs without its
   lower-bound validator.) This step is easy to get wrong — a head chosen one commit too late may
   already contain a fix and silently leak the answer.
3. **Exclude the remediation commits** from the changeset range. The gate is fed `BASE..ADVERSE_HEAD`
   only — never the range that contains the fixes or their commit messages (those messages would hand
   the gate the answer).

## 4. Inputs fed to the gate

Scope everything to `BASE..ADVERSE_HEAD`:

| Input | What it is | How to produce it |
|---|---|---|
| worktree | a detached checkout of the shipped source **at `ADVERSE_HEAD`** — the code actually under review | `git worktree add <worktree_dir> <ADVERSE_HEAD>` |
| diff | the changeset under review | `git diff <BASE>..<ADVERSE_HEAD> > <diff_file>` |
| commit messages | a primary claim source (NO remediation messages) | `git log <BASE>..<ADVERSE_HEAD> > <commits_file>` |

Optionally, a prior **design-council verdict** for the change can be fed in as an extra claim source
(each addressed `FAIL`/`CONCERN` becomes a claim to verify against the shipped code).

## 5. Running the gate

Point the gate at the worktree as the `repo_path`, with the diff and commit messages as the claim
sources, under `gate_policy: blocking-with-waiver`. Either drive it via the `/claim-guard` concierge
skill, or run the `verify-claims` recipe (full install), or — under the lightweight `--app` install —
ask the session to orchestrate the lenses and aggregate via `claim_ledger` (see the README *Usage*
section). All `file:line` anchors resolve into the worktree.

Repeat the run a few times (the acceptance used several independent repetitions) — the LLM layer is
non-deterministic, so the bar must be met **reliably**, not once.

## 6. The pass/fail bar

**Adverse run (power):**
- The gate returns **BLOCK**.
- Each of the four blockers appears as a **REFUTED** (or otherwise blocking) claim, with a `file:line` anchor
  into the worktree and a counter-case.
- Coverage is complete (no INDETERMINATE from missing lenses / empty harvest) — a BLOCK that is
  actually an incomplete run does **not** count as a pass.

**Control run (specificity):**
- Run the same gate against `FIXED_HEAD` (a worktree at the fixed head; diff/commits scoped to
  include the fixes).
- The claims corresponding to the four blockers flip to **CONFIRMED** (each now carrying the `file:line` of the
  code that keeps the promise). Claims that remain genuinely untestable statically may stay
  `UNTESTABLE` — that is honest, not a failure — but the fixed defects must no longer read REFUTED.

The acceptance is met when the adverse run **reliably** catches all four blockers and the control run
**reliably** clears the fixed ones. (Extra REFUTED claims beyond the four known blockers are expected and welcome — a
sharper gate finds more than the human did; they are reported, not penalised.)

## 7. Interpreting the result honestly

- **The deterministic core is the verdict, not the finding.** `claim_ledger` computes worst-wins
  aggregation and the BLOCK/PASS/INDETERMINATE rule mechanically; the *findings* come from the LLM
  lenses and vary run to run. Judge the gate on whether the **blocking findings reliably appear**, not
  on byte-identical output.
- **A BLOCK on the adverse state is only meaningful with the control.** Without the fixed-head
  control, a gate that always blocks would "pass" trivially. The flip-to-CONFIRMED is what proves the
  gate discriminates.
- **Evidence is the currency.** A REFUTED without a `file:line` anchor and a counter-case does not
  count — the ledger rejects unanchored CONFIRMED/REFUTED verdicts, and the acceptance holds the human
  to the same bar when reading the matrix.

## 8. Results (summary)

**Static gate — power and specificity.** On the four-blocker subject, the adverse run reliably
returned **BLOCK** and caught all four blockers every time, each with a `file:line` anchor and a counter-case;
the fixed-head control cleared the fixed defects. This was re-run against current `HEAD` after a
harvester rewrite and still holds — the gate's core catch did not regress.

**Dynamic pen-testing (Phase 2), validated in a Digital Twin.** The behavioural loop
(`probe-designer` → `pen-tester` → `regression-graduator`) was exercised end-to-end across **both**
outcomes:
- **A probe that made the forbidden violation happen** — it drove the adverse state (a degraded write
  path that could duplicate records under concurrency), observed the specific violation (not
  liveness), and recorded a **REFUTED** verdict with evidence. Correctly *not* graduated: a falsified
  probe is a new-defect finding, not a survivor.
- **A probe that survived and was graduated** — a cap claim survived its probe and was promoted into a
  standing regression test that goes red on the violation and green on the fix, runs deterministically,
  and asserts the property (not a literal). It is a real, committable pytest, and it clears the gate's
  "adverse-state test exists" requirement for that claim.

A confirming run against a **real database** (rather than an in-process model of it) reproduced the
model's numbers, showing the lighter in-process path was a faithful proxy of the real race — not a
modelling artifact.

**Harvest reproducibility.** Repeated harvests on the *same* change vary in **which** claims get
selected and **how** they are worded, so the exact claim list (and count) is **not** byte-reproducible
run-to-run. What *is* reproducible is the **category of concern** each run surfaces. The committed
harness (`scripts/harvest_stability.py`, §8.1) therefore gates on **concern-category overlap** plus a
blocker guardrail, and treats exact-claim-list identity as an indicative diagnostic, not a guarantee.
Trust the verdict and the blocker catch; treat the detailed claim list as indicative.

### 8.1 Harvest-stability harness

The harness is committed at `scripts/harvest_stability.py`. It does **not** run the harvesters itself
(that is an LLM step, run in a Digital Twin per §9's never-install-locally rule); it **consumes the
`ledger.json` files** those repeat runs produce and scores their agreement. It imports the real
identity/normalization code, so its claim ids match the ledger exactly — which also lets it detect the
harvesters drifting from the canonical claim form the normalizer expects.

```bash
# Primary gate: concern-category overlap + blockers caught; exact-id metrics printed as indicative.
python scripts/harvest_stability.py <run1>/ledger.json <run2>/ledger.json ... \
    [--min-concern-overlap 0.8] \
    [--require-blocker degraded-boot --require-blocker cap-inversion ...] [--json]

# Strict (opt-in): re-enable the exact-identity bar to measure it on demand.
python scripts/harvest_stability.py <run1>/ledger.json ... \
    --strict-ids --min-jaccard 0.9 --min-id-stability 0.9

# Self-check the metric itself on synthetic claim sets (no ledgers needed):
python scripts/harvest_stability.py --selftest
```

Exit code is **0 iff the active gate (primary concern-category overlap, or the exact bar under
`--strict-ids`) plus the blocker guardrail are met**, 1 otherwise — suitable for wiring into an
acceptance run over N≥5 ledgers from repeat harvests on ONE changeset.

## 9. Where the runs live (and what is never committed)

Raw evaluation artifacts — worktrees, diffs, ledgers, matrices, and per-run logs — live **outside this
repo** in an untracked location, and are **not** committed. They contain full run transcripts and
machine-specific paths; keeping them out of the repo is deliberate.

**Committed:** this methodology document and the harness only.
**Never committed:** raw run output, the reconstructed worktrees, per-run ledgers/matrices, absolute
machine paths, and any provider/model or credential data.

To reproduce, recreate the `BASE / ADVERSE_HEAD / FIXED_HEAD` reconstruction on your own subject PR
per §3–§6 and keep your runs in an untracked location.

## 10. Install-target and usability notes

Two things worth knowing, both verified on a real host (not a twin):

- **Install the root bundle, not a bare behavior.** Adding a bare behavior file with `--app` registers
  an empty stub that composes nothing. Install the root bundle:
  `amplifier bundle add "git+…/amplifier-bundle-claim-guard@main" --app`.
- **Layering the bundle does not hijack the host.** A registered mode is inert until activated —
  layering claim-guard onto any host bundle never blocks the host's editing until you activate
  `/claim-guard`. With the mode active, the write-fence applies; with it inactive, ordinary editing
  works. The end-to-end gate drive (harvest → independent lenses → deterministic `claim_ledger`
  verdict) was confirmed live on a small adverse sample: a claim that the code did not keep was
  **REFUTED** by both a static lens and the empirical lens (which actually executed the code), and the
  gate returned **BLOCK** with the counter-case; the proposed fix was surfaced, not applied.
