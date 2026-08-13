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

## 8. Where the runs live (and what is never committed)

Raw evaluation artifacts — worktrees, diffs, ledgers, matrices, and per-run logs — live **outside
this repo**, under a workspace-local `.amplifier/evaluation/claim-guard/` tree, and are **not
committed**. They contain full run transcripts and machine-specific paths; keeping them out of the
repo is deliberate.

**Committed:** this methodology document only.
**Never committed:** raw run output (`run.jsonl`/logs), the reconstructed worktrees, per-run
ledgers/matrices, absolute machine paths, and any provider/model or credential data.

To reproduce, recreate the `BASE / ADVERSE_HEAD / FIXED_HEAD` reconstruction on your own subject
PR per §3–§6 and keep your runs in an untracked location.
