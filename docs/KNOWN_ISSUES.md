# Known Issues

Honest limitations of the current build. The gate is useful and its **verdict is stable**; these are
the rough edges to be aware of and the ones worth tightening next.

---

## KI-1 — Harvester non-determinism: FIXED, pending empirical (in-twin) confirmation

**Status:** root cause addressed on both axes; the deterministic half is unit-proven and the
stability harness + pre-fix baseline are in place. The one remaining step is the **N≥5 live harvest
run in a Digital Twin** to confirm the *post-fix* reproducibility clears threshold — **not yet done.**
Do not read this as fully closed until that measurement lands.

**What it was.** Across repeated runs on the *same* changeset, the two harvester agents
(`claim-harvester`, `purpose-inquisitor`) produced **different claim counts** — observed
**18 / 77 / 22 / 11** across four runs. The variance was in how the change was *decomposed* into
claims (**granularity**) and how each claim was *phrased* (**phrasing**), not in the underlying
facts. Phrasing variance was the sharper problem: the ledger's stable `claim_id` (design finding
F-9) is a hash of normalized claim text + type + source, so a reworded restatement of the same claim
hashed to a *different* id and defeated run-to-run matrix diffing. Throughout, the **top-line verdict
stayed stable (BLOCK)** and **all four incident blockers (B-1…B-4) were caught every run** — the gate
did its job; only the detailed matrix was non-reproducible.

**The fix (both axes).**

1. **Code-level — `identity.py` normalization hardening.** `normalize_text` is now a canonical-form
   pipeline (NFKC → code/prose segmentation with code-token preservation → casefold → closed
   contraction map → punctuation→space → a small closed filler set) that collapses trivial rewordings
   to one `claim_id` **without** over-collapsing distinct claims. The **R-1 over-collapse tripwire** —
   a minimal-pairs suite asserting negation flips, quantifier/bound changes, subject/object swaps,
   different identifiers, and modal changes all keep **distinct** ids — is part of the suite.
2. **Prompt-level — harvesters emit a canonical form against a shared contract.** Both agents now
   obey a single **claim contract** factored into the shared `claim-harvesting` skill (so prompt and
   normalizer cannot drift — spec risk R-6): the **atomicity rule** (one load-bearing assertion per
   claim; explicit split/merge criteria; claim count = distinct mechanism × distinct
   forbidden-property) and a **canonical claim-statement form** (subject–predicate, present tense,
   symbol-named, controlled vocabulary) that the normalizer is built to reward.
3. **Determinism knob — `temperature: 0`** pinned on the two harvest steps of `verify-claims.yaml`
   (a variance reducer, necessary but not sufficient; the durable reproducibility comes from #1 + #2).

**What is PROVEN now (deterministic, unit-level):**

- the `identity.py` canonical-form invariants including the R-1 minimal-pairs over-collapse tripwire —
  the full `tool-claim-ledger` suite (**118 tests**) passes;
- the stability harness `scripts/harvest_stability.py` is committed and its `--selftest` passes;
- the harness **correctly scores the pre-fix evaluation ledgers as FAIL** — **mean pairwise
  Jaccard@claim_id 0.0, claim_id stability 0.0, count 11–77**. That 0.0 / 0.0 is the recorded
  **"before"** the fix must beat, and confirms the metric is sensitive to exactly this failure.

**What REMAINS (the acceptance measurement — not yet done):** the **N≥5 live harvest run** on one
fixed changeset, in a Digital Twin (per the never-install-locally rule), to confirm the *post-fix*
live **Jaccard@claim_id** and **claim_id stability** clear the ≥0.9 thresholds while B-1…B-4 stay
caught every run. The harness (`scripts/harvest_stability.py`) consumes the N `ledger.json` files and
exits 0 iff the thresholds and the blocker guardrail are met. Because it imports the real
`identity.py`, it will also catch any residual prompt↔normalizer drift (R-6). See
`EVALUATION.md` §9 "Harvest stability (KI-1)" for the metric definitions, invocation, and status.

**Scope / non-goals (unchanged).** This was always a *reproducibility* limitation, not a *correctness*
one — the deterministic core (`claim_ledger` worst-wins aggregation + the gate rule) faithfully
computes a verdict over whatever claim set it is given, and extra claims beyond B-1…B-4 are welcome.
Until the in-twin measurement lands: **the code fix is proven and the harness is ready; treat the
live reproducibility as fixed-pending-confirmation, and keep trusting the verdict and the
blocker-catch in the meantime.**

---

## KI-2 — Phase 2 behavioural loop not yet exercised end-to-end on a real target

The dynamic bench (`probe-designer` → `pen-tester` → `regression-graduator`) and the `probe-claims`
recipe are **built, committed, and DTU-validated for composition, recipe parse, and `claim_ledger`
round-trip** (see `EVALUATION.md` §"Phase 2 validation (DTU)"). The **full behavioural loop** — stand
an adverse state up in a Digital Twin, attack it, and graduate a surviving probe into a standing test
— is the intended per-changeset use and has **not yet been run end-to-end on a real target changeset**.
The follow-up to do so (reachable provider inside the twin, nested Incus/Docker for adverse states, a
target changeset + a `verify-claims` ledger present, probe budget) is documented in `EVALUATION.md` as
the next exercise, not claimed as done.
