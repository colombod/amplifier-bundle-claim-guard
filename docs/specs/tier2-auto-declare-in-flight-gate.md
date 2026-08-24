# Tier-2 spec — auto `work_declare("awaiting_human")` while a bound gate is in flight

Status: **SPEC ONLY** (no cross-repo code change until agreed). Depends on the Tier-1 binding
(`tier1-run-id-item-id-binding.md`) for the `item_id ↔ run_id` link. Source:
`FINDINGS-work-tracker-x-claim-guard.md` §F2/F3.

## Problem

work-tracker custody renews on a **15-minute TTL**; an unrenewed hold is reclaimed. A claim-guard
gate cycle is not a 15-minute operation:

- Measured gate cycles ran **18–59 minutes** (harvest → cold fan-out → debate → re-gate), against
  the 15-min TTL, with **zero `work_declare` signalling**.
- **Incident i15:** a BLOCK held an item an extra **~48 minutes** through a BLOCK → waive → re-gate
  tail with **nothing signalling why** — a legitimately long hold that was indistinguishable from a
  hung or abandoned one.

`awaiting_human` (via `work_declare`) suppresses the human-attention notification and makes a long
hold *legible* — but today a human/agent must remember to call it, and the programme shows they
don't. The custody clock still runs regardless (declaring renews the signal but does not exempt the
hold from reclaim — see the awareness note), so the real requirement is twofold: **declare
automatically at the moments a gate goes long, and keep renewing custody underneath.**

## The two in-flight states that must auto-declare

For a held item with a bound run (Tier-1), the flow auto-`work_declare("awaiting_human")` at these
transitions — the agent never has to remember:

1. **Gate BLOCK.** The instant `report`/`gate` returns `verdict == BLOCK` for the bound run, declare.
   A BLOCK means fix-or-waive-then-re-gate — inherently human-paced. This is the i15 case.
2. **Waive-pending.** When the flow surfaces a claim for a human waive decision (an
   `UNTESTABLE-unwaived` block the human must adjudicate, or any REFUTED the human must rule on),
   declare before handing off.

Return to `work_declare("working")` automatically when the human's input arrives and the flow
resumes (fix applied, re-gate starting). The declared state is thus an honest mirror of whether the
hold is waiting on a person or actively progressing.

## Custody-TTL vs gate-duration guidance

- **Declaring is not a TTL exemption.** `awaiting_human` suppresses the *notification*, not the
  reclaim clock. The underlying custody renewal (the background PID-bound heartbeat) must keep
  running throughout the gate — this is what keeps an arbitrarily long *idle-on-human* hold alive
  while a genuinely *dead* hold still gets reclaimed. The spec does not lengthen the 15-min TTL.
- **Escalation ceiling still applies.** A *fresh* `awaiting_human` hold is reclaim-eligible after the
  escalation ceiling (default 24h) regardless — so a forgotten parked item is not immortal.
- **Recommended relationship:** custody renewal interval (default 120 s) ≪ TTL (15 min) ≪ typical
  gate cycle (18–59 min) ≪ escalation ceiling (24 h). The renewal keeps custody; the auto-declare
  keeps the *reason* legible; the ceiling bounds neglect. No knob needs changing — only the
  automatic declare needs adding.

## Interaction with Tier-1

Tier-1's gate-aware `work_resolve` refuses on a BLOCK bound run; Tier-2 ensures that same BLOCK is
declared `awaiting_human` at the moment it happens. Together: a BLOCKed item **cannot** be silently
resolved (Tier-1) **and** is **visibly parked** rather than silently-long (Tier-2). i15 is closed by
the pair.

## Migration

1. Land Tier-1 binding (so the flow knows which run is bound to the held item).
2. Add the auto-declare hooks at the BLOCK and waive-pending transitions (work-tracker × claim-guard
   glue; additive). Until then, the `work-tracker-with-claim-guard` skill rule 3 ("Park legibly")
   is the manual bridge — it already instructs `work_declare("awaiting_human")` on BLOCK.

## Out of scope

Changing the TTL, the renewal interval, or the escalation ceiling — the defaults are correct; the
gap is a missing *automatic* declare, not a mis-tuned clock.
