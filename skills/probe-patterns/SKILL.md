---
name: probe-patterns
description: "Per-claim-type probe design patterns for Phase-2 behavioural penetration testing — how to turn a quantitative / temporal / concurrency / safety claim into a falsification experiment in a Digital Twin that observes for the SPECIFIC violation (corruption/loss/inversion/staleness), never liveness. Use when the probe-designer is designing a probe or the pen-tester is standing one up."
model_role: reasoning
---

# Probe Patterns

A probe is an experiment that tries to make a claim **FALSE** in the one condition it exists to
survive. This skill maps each probe-eligible claim type to a concrete experiment shape. It is the
Phase-2 companion to `adverse-state-catalog` (which names the adverse states) and
`properly-delivered-claim` (which defines when a probe becomes a durable test).

**The one rule that governs every pattern:** the assertion observes for the **specific forbidden
violation** — corruption, loss, inversion, or staleness — and goes **RED on that violation**. A probe
that checks "the process stayed up" or "returned 200" is not a probe; it is a liveness check wearing
a probe's clothes.

## Pattern by claim type

### `quantitative` — "stays under N" (tokens / ms / rows / bytes)
Reading accepts a plausible estimate; only measurement is trustworthy (the seed's ~23–26K estimate
was really ~36–39K — a 50% miss that a code read waved through).
- **Adverse state:** the realistic worst-case input, not the demo input — the largest session, the
  deepest recursion, the biggest batch.
- **Exercise:** run the real path under that input in the DTU.
- **Assertion (inversion):** `measured <= N`. Goes RED when the real measurement exceeds the bound.
  Capture the actual number — the value *is* the evidence.

### `temporal` — "self-clears / re-probes / eventually" (THREE-PHASE, always)
A single snapshot cannot catch a latch. This is the shape the `schema_health`-computed-once latch
requires.
- **Phase 1:** drive the system into the degraded/tripped state; observe the gated behaviour.
- **Phase 2:** repair the underlying condition **out-of-band** (fix the graph, restore the
  dependency) — WITHOUT restarting the process.
- **Phase 3:** observe **again, in the same process/PID.**
- **Assertion (staleness):** the second observation reflects the repair. Goes RED if the signal is
  latched from Phase 1. A one-shot probe here is a false negative by construction — reject it.

### `concurrency` — "idempotent under retry / no duplicates under race"
The bug lives in the interleaving, not the source line.
- **Adverse state:** transient-failure-then-success (fail once, succeed on retry within budget), or
  two writers on the same logical entity concurrently.
- **Exercise:** force the interleaving — a flush that deadlocks then retries green; two concurrent
  MERGEs on the same key.
- **Assertion (corruption/duplication):** the invariant count holds — e.g. `count(Iteration)==1`
  after a transient-fail-then-succeed, `count(duplicate :Node)==0` after a race. Goes RED on the
  extra row. Run it enough times to defeat luck; determinism is the graduator's bar, but a
  concurrency probe that passes once and fails once has already proven the claim false.

### `safety` — "X cannot happen / we prevent Y / won't corrupt"
Absence of a gate is provable statically; **presence of real protection is only proven by attacking
the adverse state.**
- **Adverse state:** remove the invariant-enforcing mechanism (drop the constraint), or feed the
  boundary value the missing validator would have rejected.
- **Exercise:** drive the write/delete/mutation path in that state.
- **Assertion (the forbidden violation):** the specific bad outcome does not occur — no duplicate, no
  lost write, no inverted cap. Goes RED when it does. If the violation occurs, the safety claim is
  empirically REFUTED — a new defect.

## Falsifiability and the pre-change baseline

- Every probe must have a **red-before/green-after** story: it must be able to FAIL on the pre-change
  code and PASS on the post-change code. If it passes on both, it exercises nothing (the over-fit
  `node_count==1`-because-the-fixture-seeded-one trap) — it will be rejected at graduation. Design the
  assertion against the *property*, not the fixture's incidental values.
- If you cannot construct an adverse state or an observable violation, the claim is **not
  falsifiable** — record that as a finding. A claim you can't test is a claim you can't trust; it
  routes to human adjudication, and a safety claim in that state still trips the gate.

## Where probes run and what they leave behind

- Probes run in an **isolated Digital Twin** (`digital-twin-universe`) — never against production or
  the host. Build the adverse world there; it is also, reliably, a defect engine (constructing it
  exercises adjacent paths and surfaces defects nobody claimed).
- The executable probe and its captured output are artifacts under `.claim-guard/<run-id>/probes/`;
  new defects under `.claim-guard/<run-id>/new-defects/`; graduated candidate tests under
  `.claim-guard/<run-id>/proposed-tests/`. The gate-moving signal reaches the ledger via
  `record_verdict` (verdict + `adverse_state_test`), not by writing a raw probe blob into the ledger.
