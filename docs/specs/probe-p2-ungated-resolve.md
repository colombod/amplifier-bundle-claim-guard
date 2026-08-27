# Probe P2 — `work_resolve` succeeds with a BLOCK/absent bound gate (the core seam gap)

## Origin

- **Safety claim:** `clm_15bd48c0` (umbrella).
- **Findings:** F4, G5.

The two systems — **work-tracker** and **claim-guard** — can silently disagree,
because `work_resolve` has **ZERO knowledge of claim-guard**. An item can be
resolved while its bound claim-ledger run is `BLOCK`, or while it was never
gated at all. Nothing in the resolve path consults the ledger, so the seam
between the two stores is unenforced.

## Adverse state (two-store)

A work-tracker item in state **HELD**, bound — *by convention: one `run_id` per
`item_id`* — to a claim-ledger run driven into one of two arms:

| Arm | Ledger run state |
|-----|------------------|
| **A** | `gate` = **BLOCK** |
| **B** | never-gated-with-claims (**stranded**) |

## Exercise

Call `work_resolve` on that held item.

## Red-on-violation assertion

**The item must NOT be resolved.**

The oracle reads ground truth from **both stores**:

1. **Claim-ledger** — the run's gate state, via `list_runs`
   (`last_verdict` / `gated`). These fields exist because `op_gate` now
   persists gate history.
2. **Work-tracker** — the item's `resolved` state.

The assertion fires (RED) when the item is resolved despite the bound run being
`BLOCK` (arm A) or never gated (arm B).

## Honest RED-before / GREEN-after

**TODAY the assertion FAILS.** `work_resolve` succeeds regardless of the bound
gate → **RED = the gap is present, in both arms.**

It flips **GREEN only when a gate-aware `work_resolve` refusal lands**, tracked
as item **`e9n`** — **NOT YET IMPLEMENTED**.

Therefore this probe is a **RED-before finding that CANNOT be graduated GREEN
yet**. It graduates together with `e9n`; it is not a standing regression test
until then.

## Relationships

- **`e9n`** — the fix (gate-aware `work_resolve` refusal). This probe graduates
  with it.
- **`xrq` / P3** — the session-end sibling of this probe.
- **Combined-skill rule 1** — *gate-before-resolve*, currently only a **manual
  bridge** between the two systems.
