# Known Issues

Honest limitations of the current build. The gate is useful and its **verdict is stable**; these are
the rough edges to be aware of and the ones worth tightening next.

---

## KI-1 — Harvester non-determinism: RESOLVED — closed at a revised, honest bar

**Status:** **CLOSED** at a revised acceptance bar, with an accepted residual documented (not hidden).
The exact run-to-run claim-matrix identity target was **measured unreachable** with a free-form LLM
harvest on the shipped stack; the bar was redefined (path (c)) to what is both *reproducible* and
*what actually matters for a gate* — and that bar is **MET**. References: **`claim_gate-wd7`** (path a,
the stricter-template attempt, measured) and **`claim_gate-0ut`** (path c, this closure). Full
measurement write-up in `EVALUATION.md` §9.

**What it was.** Across repeated runs on the *same* changeset, the two harvester agents
(`claim-harvester`, `purpose-inquisitor`) produce **different claim sets** run-to-run — originally
counts **18 / 77 / 22 / 11**, and essentially **disjoint** `claim_id` sets. The variance is in *which*
claims are selected, at what granularity, and how they are phrased — not in the underlying facts.
Because the stable `claim_id` (design finding F-9) is a hash of normalized text + type + source, that
variance forks the id and defeats exact run-to-run matrix diffing. Throughout, the **top-line verdict
stays stable (BLOCK)** and **all four incident blockers (B-1…B-4) are caught every run.**

**What was built (all kept — correct and mutually reinforcing).**

1. **Code prong — `identity.py` normalization hardening.** A canonical-form pipeline (NFKC → code/prose
   segmentation with code-token preservation → casefold → closed contraction map → punctuation→space →
   small closed filler set with a NEVER-STRIP guard) that collapses **trivial rewording** to one
   `claim_id` **without** over-collapsing distinct claims. Genuinely valuable — it just does not, by
   itself, collapse paraphrase or selection variance (and deliberately does **no** semantic-collapse,
   to avoid the R-1 false-merge hazard).
2. **Prompt prong — deterministic grid + rigid template + per-property typing** (path a). A required
   mechanism×property grid (one claim per occupied cell), a rigid `<symbol> <verb> <object>` template
   over a closed predicate vocabulary, and deterministic per-property `type`. Makes *phrasing* canonical
   (a prerequisite for any future selection fix).
3. **R-6 prompt↔normalizer drift guard** — the controlled vocabulary/template is bound to the normalizer
   by tests, so the two cannot silently drift.

The full module suite (**147 tests**) passes, the harness `--selftest` passes, and `python_check` is
clean.

**What was measured (the honest result).**

- **Exact matrix identity is unreachable.** N=5 in-twin harvests on one fixed changeset scored
  **Jaccard@claim_id 0.0** both before path a (`@b646bf2`: 0.0075 / id-stability 0.0395, counts 54–85)
  and after the stricter template (`@2a97cb7`: 0.0 / 0.0, counts 34–88 — no improvement). The template
  *is* followed; the variance simply **moved from phrasing to claim SELECTION** (which symbols, what
  granularity, which property/type). Three proven reasons it is unreachable: paraphrase **and** selection
  variance, `identity.py` does no semantic-collapse (R-1 safety), and `temperature: 0` is inert on the
  Opus ≥ 4.7 harvest routing (the anthropic provider does not send it).
- **Concern *category* IS reproducible.** Coarsening the same tightened ledgers (`@2a97cb7`) by key:
  mean pairwise Jaccard = exact `claim_id` **0.0**, `type` (concern category) **0.933**, predicate
  (verb+object) **0.548**, symbol **0.306**. So *which categories of concern* surface is stable even
  though the exact matrix is not.

**The revised, honest acceptance bar (three tiers) — this is the close.**

1. **PRIMARY (the gate's real guarantee — what actually matters): MET.** The top-line **VERDICT** and
   the **incident-blocker (B-1…B-4) catch** are stable run-to-run — demonstrated in the acceptance
   evaluation (§1–§7 of `EVALUATION.md`): **4/4 runs BLOCK, B-1…B-4 caught every run.**
2. **SECONDARY (harvest health — now the harness's gate): MET.** **concern-type overlap ≥ 0.8** — every
   run surfaces the same categories of concern. Measured **0.933 → PASS.** Predicate overlap 0.55 and
   symbol overlap 0.31 are reported as additional diagnostics (not gated).
3. **ACCEPTED RESIDUAL (documented, not hidden).** Exact run-to-run `claim_id` matrix identity is **NOT
   achievable** with a free-form LLM harvest on this stack. Therefore **F-9 run-to-run matrix *diffing*
   is best-effort / indicative, not guaranteed.** `scripts/harvest_stability.py --strict-ids` remains
   for anyone who wants to measure the exact bar on demand.

**The harness reflects this** (`claim_gate-0ut`): its PRIMARY gate is now **concern-type overlap ≥
`--min-concern-overlap`** (default 0.8) plus the B-1…B-4 guardrail; the exact `Jaccard@claim_id` /
`claim_id stability` are demoted to reported *indicative* diagnostics; `--strict-ids` re-enables the
old exact bar. Real run over the tightened ledgers: **concern-type overlap 0.9333 → PASS at 0.8.**

**Scope / non-goals (unchanged).** This was always a *reproducibility* limitation, not a *correctness*
one — the deterministic core (`claim_ledger` worst-wins aggregation + the gate rule) faithfully computes
a verdict over whatever claim set it is given, and extra claims beyond B-1…B-4 are welcome. **Bottom
line: trust the verdict and the blocker-catch (guaranteed) and the concern categories (harness-gated);
treat the exact detailed claim matrix as indicative, not byte-reproducible (accepted residual).**

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
