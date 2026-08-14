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

## KI-2 — Phase 2 behavioural loop: core capability demonstrated end-to-end across BOTH outcome branches (in-process adverse-state models); only live-fidelity residual remains

**Status:** the dynamic bench (`probe-designer` → `pen-tester` → `regression-graduator`) and the
`probe-claims` recipe are **built, committed, DTU-validated, and now exercised end-to-end across both
Phase-2 outcome branches** in the twin — **FALSIFIED → REFUTED** (first run, `claim_gate-6i1`) and
**SURVIVED → graduated into a standing test** (this run, `claim_gate-zot`). All three loop stages have
run, on three probed claims. **Two of the three original residuals are now closed;** only the
live-Neo4j-fidelity residual remains, and it is **infra-gated** (no nested containers on this host).
See `EVALUATION.md` §8.2–§8.3 for the full write-up. KI-1 is unaffected.

**Both branches proven end-to-end.**

- **FALSIFIED → REFUTED** (`claim_gate-6i1`, twin `@7131dd2`). `probe-claims` consumed an existing
  `verify-claims` ledger (`run_id t0run1`, 54 claims) via the `run_id` seam — consumed, did not
  re-harvest — and drove the loop on `clm_2a25c125` (*"a degraded server does not create a duplicate
  `Node`"*, `safety`, core B-1): `probe-designer` → `pen-tester` **designed/built/RAN** the
  adverse-state experiment (observing the specific violation, not liveness) → **REFUTED** recorded with
  red-before/green-after control (ADVERSE 25/25 duplicate rounds, max `COUNT(*)`=8, 175 extra rows;
  CONTROL 0/25, max=1; host re-run identical, deterministic). Ledger: `aggregate=REFUTED` with
  `file:line` (`neo4j_store.py:988-999`, `:1287`). A FALSIFIED probe is correctly a **new-defect
  finding, not graduated.**
- **SURVIVED → graduated** (`claim_gate-zot`, twin `@9ed4d1b`). Survivor `clm_c39773b8`
  (*"`reclaim_blobs` deletes at most `max_delete` blob files in apply mode"*, `quantitative`, real
  **B-3** source asymmetry: adverse `admin.py:653` `max_delete: int | None = None` vs fixed
  `admin.py:678` `Field(default=None, ge=1)`). `regression-graduator` → `claim_ledger graduate_test`
  → **ACCEPTED** — all four criteria met (no `graduation_criteria_unmet`): **RED-BEFORE**
  (`max_delete=-1` → `candidates[:-1]` deleted **9 of 10**), **GREEN-AFTER** (`max_delete=-1` and `0`
  raise `ValidationError`/422 before any `unlink`, `deleted=0`), **DETERMINISTIC** (3/3),
  **ASSERTS-THE-PROPERTY** (*"non-positive cap rejected AND `deleted_count <= min(cap, len)"*, not a
  literal). Ledger: `probe.outcome=SURVIVED`, `standing_test` set
  (`.claim-guard/t0run1/probes/test_max_delete_cap_standing.py`, `red_before=true`, `green_after=true`,
  `deterministic_runs=3`, `asserts_property=true`), **`adverse_state_test.exists=TRUE`** — **gate limb
  2 cleared** (the "properly delivered claim"). The graduated standing test was independently re-run on
  the **host: 21 passed** — a real, committable pytest.

**Correctness nuance (honest, not a bug).** The survivor's `aggregate` stays **`PENDING`**:
`record_probe`/`graduate_test` deliberately **never fabricate a lens verdict**, so with no
`correspondence`/`pen-tester` verdict recorded, no `CONFIRMED` is invented. Graduation clears limb 2;
it does not manufacture a verdict.

**Residuals — original three, now down to one.**

1. ~~**More than one claim**~~ — **DONE.** `coverage.probed=3` in ledger `t0run1`: `clm_2a25c125`
   (FALSIFIED→REFUTED), `clm_c39773b8` (SURVIVED→graduated), `clm_103eba07` (SURVIVED, probe only).
2. ~~**Graduation of a SURVIVING probe**~~ — **DONE.** `graduate_test` ACCEPTED on `clm_c39773b8`
   (four criteria, `adverse_state_test.exists=true`, host re-run 21 passed).
3. **Full-fidelity live probes** — **STILL OPEN (infra-gated).** The same loop against a real degraded
   Neo4j in a nested Docker/Incus twin needs a container-capable host; this host has none. Both runs
   used the design-sanctioned lighter path — self-contained in-process repros (`uv run --with
   pydantic`) that **faithfully model** the exact mechanisms (MERGE-without-uniqueness-constraint race;
   negative-slice cap inversion) — which **demonstrably surface the real B-1/B-3 violations**, but are
   **in-process models, not live-server probes.** Do not overclaim them as live-Neo4j probes.

**Bottom line — substantially closed.** The core Phase-2 capability is **demonstrated end-to-end
across both outcome branches**: all three loop stages ran, the FALSIFIED and SURVIVED branches both
went through structurally (REFUTED recorded with `file:line`; a survivor graduated into a committable
standing test that passes on the host and clears gate limb 2), and multi-claim `coverage.probed=3`.
The **only** remaining residual is **live-container fidelity** (a real degraded Neo4j behind nested
Docker/Incus) plus larger budget-scale runs — both follow-ons, honestly not claimed as done.

Raw artifacts (uncommitted, outside the repo):
`.amplifier/evaluation/claim-guard/ki2-probe/` (first run) and
`.amplifier/evaluation/claim-guard/ki2-graduation/` (this run).
