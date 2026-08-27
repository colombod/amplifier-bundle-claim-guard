# Probe P3 — session-end stranded state (held item + un-gated/empty-`run_id` run) goes undetected

## Origin

- **Safety claim:** `clm_15bd48c0`.
- **Finding:** G5 — a session ended holding an item with claims on an **empty
  `run_id`**, with **no gate** and **no resolve**.

## Adverse state

A **HELD, UNRESOLVED** item whose bound run has claims but was **never gated**
— or whose claims sit on an **empty `run_id`**.

## Exercise

Run the **stranded-state oracle** at the **session-end checkpoint**.

## Red-on-violation assertion

**The stranded shape must be surfaced.** The oracle reads ground truth from
**both stores**:

1. **Claim-ledger** — the run's claims and gate state.
2. **Work-tracker** — the item's held / unresolved state.

The assertion fires (RED) when a held, unresolved item with an un-gated (or
empty-`run_id`) bound run passes session end without being surfaced.

## KEY DIFFERENCE from P2

**P3's detector already EXISTS, and P3 is GREEN-after-able TODAY** — it is
**graduatable now as a standing regression test**. Three mechanisms make that
true:

1. **`list_runs(stranded_only=true)` / `stranded_count`** surfaces the strand.
2. **Empty `run_id` is now structurally rejected** — `add_claim` / `add_claims`
   reject an empty or unknown `run_id`.
3. **`op_gate` persists `gated` / `last_verdict`**, so the oracle can read gate
   ground truth rather than infer it.

The original *"goes undetected"* premise is therefore **no longer true**. The
detector exists — plus two procedural detectors: the **Phase-7 close-out** and
the **combined-skill session-end checklist**.

## Relationships

- **P2** — session-end sibling; P3 is the session-end half of the same seam.
- **Depends on:** the `stranded_only` / empty-`run_id` / gate-history semantics.
- **Does NOT depend on `e9n`** — unlike P2, P3 needs no gate-aware
  `work_resolve` refusal to graduate.
