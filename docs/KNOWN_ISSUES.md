# Known Issues

Honest limitations of the current build. The gate is useful and its **verdict is stable**; these are
the rough edges to be aware of and the ones worth tightening next.

---

## KI-1 — Harvester non-determinism: the claim matrix is not yet reproducible run-to-run

**What happens.** Across repeated acceptance runs on the *same* changeset, the two harvester agents
(`claim-harvester`, `purpose-inquisitor`) produce **different claim counts** run-to-run. Observed on
the acceptance PR: **18 / 77 / 22 / 11** claims across four runs. The variance is in how the change is
decomposed into claims and how each claim is phrased — not in the underlying facts.

**What stays stable (the important part).** Despite the count variance, across those same runs:

- the **top-line gate verdict was stable** (BLOCK), and
- **all four incident blockers (B-1…B-4) were caught** every time, as blocking (REFUTED /
  no-adverse-state-test) claims with `file:line` evidence.

So the gate reliably does its job — *"is this changeset safe to merge?"* and *"did it catch the known
blockers?"* — even though the **detailed matrix is not byte-reproducible**.

**Why it matters.**

1. **Auditability.** Two engineers running the gate on the same PR can get materially different claim
   lists. The verdict agrees; the paperwork doesn't. That makes run-to-run *diffing* of matrices
   noisy.
2. **It undercuts stable claim-ID diffing (design finding F-9).** The ledger computes a stable
   `claim_id` from normalized claim text + type + source specifically so a PR pushed-to repeatedly can
   be re-gated and the matrix diffed against the prior run. That mechanism is only as stable as the
   **harvest phrasing** — and right now the phrasing varies enough that the "same" claim can hash to a
   different id across runs, defeating the diff.

**Scope / non-goals.** This is a *reproducibility* limitation, not a *correctness* one. Extra claims
beyond B-1…B-4 are expected and welcome (a sharper harvest finds more than the human did); the problem
is that the *set* is unstable, not that any individual claim is wrong. The deterministic core
(`claim_ledger` worst-wins aggregation + the gate rule) is unaffected — it faithfully computes a
verdict over whatever claim set it is given.

**Recommended fix (future work).** Tighten the two harvester agents toward a stable decomposition:

- constrain claim **granularity** (one load-bearing assertion per claim; explicit rules for splitting
  vs merging) so the same change decomposes the same way;
- normalize claim **phrasing** further before it reaches the ledger's id hash (canonical
  subject–predicate form), so trivially-reworded restatements collapse to one stable `claim_id`;
- consider a low/zero-temperature setting for the harvest step specifically, accepting the
  determinism/coverage trade-off;
- add a harvest-stability check to the acceptance methodology (run N times, measure claim-set
  Jaccard overlap and id stability, not just the verdict).

Until then: **trust the verdict and the blocker-catch; treat the detailed claim matrix as indicative,
not reproducible.**

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
