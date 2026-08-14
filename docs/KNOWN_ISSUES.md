# Known Issues

Honest limitations of the current build. The gate is useful and its **verdict is stable**; these are
the rough edges to be aware of and the ones worth tightening next.

---

## KI-1 — Harvester non-determinism: PARTIALLY MITIGATED — reproducibility target NOT met on the shipped stack (measured); OPEN

**Status:** the fix was implemented on both axes and part of it is proven, **but the empirical
acceptance bar is NOT met.** A live N=5 in-twin measurement scored the shipped config at
**Jaccard@claim_id 0.0075 / id-stability 0.0395** against a **0.9 / 0.9** bar — a clear FAIL. KI-1 is
**OPEN**, tracked as follow-up work item **`claim_gate-ryw`**. Do **not** read the passing unit tests
as an end-to-end fix: they prove the code prong in isolation, not run-to-run reproducibility on the
live stack.

**What it is.** Across repeated runs on the *same* changeset, the two harvester agents
(`claim-harvester`, `purpose-inquisitor`) produce **different claim sets** run-to-run. Originally
observed as counts **18 / 77 / 22 / 11**; the post-fix live run (below) still shows counts
**54–85** and essentially **disjoint** `claim_id` sets. The variance is in how the change is
*decomposed* into claims (**granularity**) and how each claim is *phrased* (**paraphrase**), not in
the underlying facts. Because the ledger's stable `claim_id` (design finding F-9) is a hash of
normalized claim text + type + source, paraphrase of the same claim hashes to a *different* id and
defeats run-to-run matrix diffing. Throughout, the **top-line verdict stays stable (BLOCK)** and
**all four incident blockers (B-1…B-4) are caught every run** — the gate does its job; only the
detailed matrix is non-reproducible.

**What was implemented, and what is genuinely proven.**

1. **Code-level — `identity.py` normalization hardening (PROVEN, correct, valuable).** `normalize_text`
   is a canonical-form pipeline (NFKC → code/prose segmentation with code-token preservation →
   casefold → closed contraction map → punctuation→space → a small closed filler set) that collapses
   **trivial rewording** (case, unicode, punctuation, articles, contractions, identifier-case) to one
   `claim_id` **without** over-collapsing distinct claims. The R-1 over-collapse tripwire (negation
   flips, quantifier/bound changes, subject/object swaps, different identifiers, modal changes stay
   **distinct**) is part of the **118-test** suite, all passing. The **R-6 prompt↔normalizer drift
   guard** (13 dedicated tests) is in place. *This prong is correct and worth keeping — it just does
   not, by itself, collapse paraphrase, which is the variance that actually dominates.*
2. **Prompt-level — canonical form against a shared contract (implemented; insufficient alone).** Both
   agents obey a single **claim contract** in the shared `claim-harvesting` skill: the **atomicity
   rule** (one load-bearing assertion per claim; split/merge criteria; claim count = distinct
   mechanism × distinct forbidden-property) and a **canonical claim-statement form** (subject–predicate,
   present tense, symbol-named, controlled vocabulary). *Measured effect: the prompt prong alone does
   not force paraphrase + granularity convergence — the agents still word and split the same claim
   differently run-to-run.*
3. **Determinism knob — `temperature: 0` pinned in `verify-claims.yaml` (measured INERT on this
   stack).** The harvest routes to Claude Opus ≥ 4.7 (opus-4-8 / opus-5), and the anthropic provider
   **does not send a `temperature` for Opus ≥ 4.7** — it is silently ignored. So on any
   Opus-4.7+/Sonnet-5 deployment this prong does **nothing**; only the prompt prong is active. The pin
   is left in place because it is correct for a sampling-capable model, but it delivers no determinism
   on the current routing.

**The measured miss (real numbers).** N=5 in-twin harvests on one fixed changeset (fixed PR#70
`c324cbe`), bundle `@b646bf2`, scored by `scripts/harvest_stability.py` and independently re-scored
on host:

| Config | Jaccard@claim_id | claim_id stability | counts | 0.9 / 0.9 |
|---|---|---|---|---|
| SHIPPED (`temperature: 0` pinned) | **0.0075** | **0.0395** | 54–85 | **FAIL** |
| bare (no temp pin) | 0.0 | 0.0 | 58–101 | FAIL |

Both paths agree (essentially disjoint id sets), which is itself the empirical proof that the
temperature pin changed nothing — root cause #3 above. See `EVALUATION.md` §9.4 for the full write-up.

**Path (a) ATTEMPTED — stricter canonical form (mechanism×property grid + rigid template), and it did
NOT converge (measured `@2a97cb7`).** The prompt prong was tightened hard: a required mechanism×property
grid (one claim per occupied cell), a rigid `<symbol> <verb> <object>` template over a closed predicate
vocabulary with deterministic per-property typing, and a second-pass canonicalizer. Unit-proven (147
module tests incl. +29 template↔normalizer R-6 tests). A fresh N=5 in-twin re-measure on the same fixed
changeset scored **Jaccard@claim_id 0.0 / id-stability 0.0** (counts 34–88) — no improvement over the
0.0075/0.0395 baseline; it slightly regressed. **Root cause, now understood:** the template *is* being
followed (phrasing is canonical), but the variance simply **moved from phrasing to claim SELECTION** —
which symbols get harvested, at what granularity, and (since `type` is in the id hash) what property/type
a shared symbol is assigned. Canonicalizing *how* a claim is worded does nothing while *which* claims get
selected still varies run-to-run. The change is kept (deterministic typing + canonical phrasing + the
hardened R-6 guard are correct and are prerequisites for any selection fix), but on its own it does not
move the metric.

**Path forward (a design decision — tracked as `claim_gate-wd7` (path a, done/measured) → `claim_gate-0ut`
(path c)).** None of the options is free; this needs a deliberate call, not a quiet default:
- **deterministic claim SELECTION (the newly-identified lever)** — the real remaining variance. Force a
  mechanical enumeration (one claim per changed public symbol × property axis) with type pinned from the
  mechanism, rather than free model choice of which symbols/granularity/type to harvest.
- **stricter prompt canonical form (phrasing)** — DONE (`@2a97cb7`); necessary but not sufficient.
- **controlled semantic-collapse in `normalize_text`** — a *tightly scoped, closed-list* synonym /
  stem step. **Risky:** this is exactly the R-1 false-merge hazard the code prong was deliberately
  built to avoid; any such step must be gated behind an expanded minimal-pairs tripwire.
- **revised threshold** — accept that full run-to-run id-identity is unattainable with LLM harvesters
  and re-define the acceptance bar (e.g. semantic-overlap rather than id-identity). Honest, but
  changes what "reproducible" means.
- **sampling-capable model pin** — pin the harvest to a model that actually honors `temperature: 0`,
  making the (currently inert) determinism prong live. Trades harvest quality/coverage for determinism.

**Scope / non-goals (unchanged).** This is a *reproducibility* limitation, not a *correctness* one —
the deterministic core (`claim_ledger` worst-wins aggregation + the gate rule) faithfully computes a
verdict over whatever claim set it is given, and extra claims beyond B-1…B-4 are welcome. **Until
`claim_gate-ryw` is resolved: the code prong (trivial-rewording collapse) and the drift guard are
proven and worth keeping, but end-to-end run-to-run matrix reproducibility is NOT achieved — trust
the verdict and the blocker-catch; treat the detailed claim matrix as indicative, not reproducible.**

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
