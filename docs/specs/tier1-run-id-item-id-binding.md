# Tier-1 spec — `run_id ↔ item_id` binding + gate-aware `work_resolve`

Status: **SPEC ONLY** (no cross-repo code change until agreed). Source: the
work-tracker × claim-guard tuning programme (`FINDINGS-work-tracker-x-claim-guard.md`).
This is the enforcing north-star for which the `work-tracker-with-claim-guard` skill is
the *bridge that works today*.

## Problem

work-tracker owns **custody** of an item (`work_claim → work_declare → work_resolve`).
claim-guard owns **verification** of a change (`start_run → gate → PASS/BLOCK`). They share
**no identifier and no enforcement**: nothing makes a gate PASS a precondition for resolving
the item it verified, and nothing ties a ledger run to the held item. Every measured failure
clustered in that seam. Two named incidents this spec must prevent:

- **G6 (un-gated resolve).** An item was `work_resolve`d beside a ledger run that had never
  reached a gate — the resolution asserted verified work that was never verified.
- **G5 (stranded).** A session ended holding an item whose bound run had claims but no gate
  (or claims on an empty/forked `run_id`), and nothing detected the disagreement.

## Enablers already delivered (this spec now rests on real mechanism)

- **`cgq`** — `add_claim`/`add_claims` reject an empty/omitted `run_id` (no silent fork). A
  binding can no longer be lost to a blank id at the claim-write seam.
- **`n5g`** — `op_gate` persists gate-invocation history; `list_runs` surfaces
  `gated` / `last_verdict` / `last_gate_at`. **"Was this run gated, with what verdict?" is now
  answerable from the ledger alone** — the missing fact that made gate-aware resolve impossible.
- **`d9k`** — `list_runs(stranded_only=true)` + `stranded_count` make a harvested-but-ungated
  run a queryable state.

## The binding — data model

One `run_id` is bound to one `item_id` for the item's life.

1. **Storage (authoritative, work-tracker side).** The work item record gains an optional
   `bound_run_id` field. `work_claim` returns it (initially null); a new `work_bind(item_id,
   run_id)` sets it exactly once (idempotent if the same id; refuses a second, different id —
   "one run per item"; if the work splits, split the item).
2. **Convenience (claim-guard side).** `claim_ledger start_run` MAY accept an optional
   `item_id` recorded into the run record's metadata (informational back-reference only — the
   authoritative binding lives on the work item). `start_run` still issues the `run_id`;
   callers never invent one (unchanged).
3. **Bridge compatibility.** Until `work_bind` lands, the binding is a written
   `run_id ↔ item_id` line in `SCRATCH.md` / the item's `design` field (today's skill rule).
   The field-backed binding supersedes the note without breaking it.

## Gate-aware `work_resolve` — the refuse/warn rule

`work_resolve(item_id, reason)` consults the bound run's **persisted** gate state (via the
ledger's `list_runs` / a `gate_status(run_id)` read, using `n5g`'s `last_verdict`):

| Bound run state | `work_resolve` behavior |
|---|---|
| `last_verdict == PASS` | **Allow.** Auto-annotate (below). |
| `last_verdict == BLOCK` | **Refuse** (no override). Prevents **G6**. Message names the blocking count. |
| `last_verdict == INDETERMINATE` | **Refuse.** Coverage incomplete — not a clean pass. |
| never gated (`gated == false`) but has claims | **Refuse.** Prevents **G6/G5** — a harvested run must be gated. |
| no bound run at all | **Warn** (policy-selectable refuse). A resolve with zero verification is legal only for items that declared no gate is needed. |

Policy knob `resolve_gate_policy: warn | block` (default `block`) mirrors claim-guard's own
`blocking`/`advisory` split, so a team can adopt incrementally.

## Auto-annotation format

On an allowed resolve, `work_resolve` appends a machine-generated trailer to the resolution
text, read from the ledger (never retyped by the agent):

```
--- claim-guard gate ---
run_id: <bound_run_id>
verdict: PASS
coverage: harvested=<h> verified=<v> probed=<p> deferred=<d> waived=<w>
gated_at: <last_gate_at>
```

This makes every resolution self-describing and removes the "did they actually gate it?"
question from review. Prevents the class behind **G6** by construction.

## Auto-`work_declare` on BLOCK

Complements Tier-2 (`z52`): when a bound gate returns BLOCK, the flow auto-`work_declare(
"awaiting_human")` so a long BLOCK→fix→re-gate tail is legible rather than silently-long
(closes the ~48-min unexplained hold observed in the programme). Specified in `z52`; named here
because the binding is its prerequisite.

## Migration

1. Land `n5g` (done) — persisted gate state. **Prerequisite; satisfied.**
2. Add `bound_run_id` + `work_bind` (work-tracker repo, additive, backward-compatible).
3. Add the gate-aware `work_resolve` read + `resolve_gate_policy` (default `warn` for one
   release, then `block`).
4. Retire the `SCRATCH.md` binding note in the skill once the field-backed binding ships; the
   skill becomes the usage guide for the enforced mechanism.

## Out of scope

Routing an empty `run_id` to "the currently-open run" (would need session state) — the delivered
`cgq` fix rejects empty instead, which is the correct floor. Cross-session multi-driver
coordination remains advisory (`work_status`/`work_list` before claiming).
