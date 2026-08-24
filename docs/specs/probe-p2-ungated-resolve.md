# Probe P2 spec — `work_resolve` succeeds with a BLOCK/absent bound gate

Status: **PROBE SPEC** (adverse-state regression probe; the fix it guards is Tier-1 `e9n`).
Source: gate safety claim `clm_15bd48c0` (umbrella) + findings F4/G5. Adverse-state category:
**cross-replica / cross-system disagreement** (`adverse-state-catalog` §"the two stores disagree").

## The forbidden violation

The two systems can **silently disagree**: `work_resolve` today has *zero* knowledge of
claim-guard, so an item can be marked resolved — asserting verified work — while its bound
claim-ledger run is **BLOCK** or was **never gated**. The probe must go **RED when the resolve is
allowed** in that adverse state, and **GREEN only when a gate-aware `work_resolve` refuses it**.
This is a disagreement/inversion assertion, never a liveness check.

## Adverse state (stand this up)

Two independent stores, per the both-store DTU pattern already used in the programme:

- **work-tracker store:** a project with one item, `work_claim`ed and held by the driver.
- **claim-ledger store:** a run bound to that item (`run_id ↔ item_id`, per Tier-1's binding, or the
  SCRATCH note in the bridge era), driven into one of the two adverse conditions:
  - **Arm A — BLOCK:** record a REFUTED verdict on a claim in the bound run; `gate` → `BLOCK`.
  - **Arm B — never gated:** harvest ≥1 claim into the bound run but **never** call `gate`/`report`
    (`n5g`'s `list_runs` shows `gated == false`, `stranded == true`).

## Exercise

With the bound run in each adverse arm, the driver calls `work_resolve(item_id, reason)`.

## Observation — the red-on-violation assertion

Read **both** stores after the call (a stranded-state oracle reading ground truth, not the driver's
own claim):

```
assert work item status != "resolved"        # the resolve was REFUSED
# i.e. RED (violation present) if the item is resolved while:
#   Arm A: bound run last_verdict == BLOCK          (via claim_ledger list_runs / gate_status)
#   Arm B: bound run gated == false AND has claims   (n5g / d9k stranded)
```

- **Today (no gate-aware resolve):** the assertion FAILS — `work_resolve` succeeds, the item is
  `resolved`, both arms RED. **That RED is the finding**: it documents the exact seam gap `e9n`
  must close.
- **After `e9n` lands:** `work_resolve` consults the bound run's persisted `last_verdict`
  (`n5g`) and **refuses** in both arms — the item stays held, the assertion passes, GREEN.

The probe is authored so the ONLY thing that flips it from RED to GREEN is the gate-aware
`work_resolve` refusal — not a change to the test's incidental values.

## Why this is now buildable as a real regression test

`n5g` made the bound run's gate verdict **persisted and queryable** (`list_runs.last_verdict` /
`gated`), so the oracle can read "was this gated, with what verdict" from ground truth in both
stores — the fact that was previously only in the driver's head (the earlier probe used a
`gate_log.jsonl` stand-in). The oracle no longer needs a side-channel.

## Graduation criteria (to become a committed standing test)

Per `properly-delivered-claim`: (1) asserts the property (item-not-resolved-under-BLOCK/ungated),
not incidental values; (2) **RED before** — fails against current `work_resolve`; (3) **GREEN
after** — passes once gate-aware resolve lands; (4) deterministic across ≥3 runs. Until `e9n`
ships, this probe is a **RED-before finding on record**, not yet graduated (it cannot be GREEN-after
against code that does not exist) — so it is filed as the standing regression that graduates
together with `e9n`.

## Relationship to other items

- **`e9n`** — the fix this probe guards (gate-aware `work_resolve`).
- **`xrq` (Probe P3)** — the session-end stranded-state probe; P2 is the resolve-time sibling (P2:
  "resolve happened wrongly"; P3: "session ended with the disagreement undetected").
- **combined-flow skill rule 1 (gate-before-resolve)** — the manual discipline that stands in for
  this enforcement until `e9n` lands.
