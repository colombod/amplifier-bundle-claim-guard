---
name: work-tracker-with-claim-guard
description: "The combined-flow procedure for a session that both claims work from a work-tracker queue AND gates its changes through the claim-guard adversarial verification gate. Use whenever you hold a work-tracker item and will run (or have run) a claim-guard gate before resolving it — it binds one run_id to the held item, makes gate-PASS a precondition for work_resolve, keeps a long gate legibly parked, and forbids the stranded-state that leaves the two systems silently disagreeing. Load at claim time, not at resolve time."
model_role: reasoning
---

# Work-Tracker × Claim-Guard: the combined flow

Two independent systems are in play whenever you gate claimed work:

- **work-tracker** owns *custody* of an item (`work_claim` → `work_declare` → `work_resolve`).
- **claim-guard** owns *verification* of the change (`start_run` → gate → PASS/BLOCK).

(For the full custody discipline — TTL/renewal, reap recovery, empty-queue handling, declared
states — load the `claiming-work-safely` skill; this skill only adds the claim-guard binding on top
of it. For the gate mechanics themselves, load `claim-guard-here`.)

They share **no identifier and no enforcement**. Nothing makes a gate PASS a precondition for
resolving the item it verified; nothing tells work-tracker that a held item is parked mid-gate;
nothing stops an item resolving beside an abandoned ledger run. In the programme that motivated this
skill, *every* failure clustered in exactly that seam — the place where the two systems' state can
**silently disagree**.

**What this optimises for:** make the seam legible and self-checking with the lightest possible
mechanism — a practice, not module code — so the two systems cannot drift apart unnoticed, while
preserving the payoff that makes the pairing worth it (a persisted ledger that re-verifies whole
programmes in seconds; a gate that sharpens the resolution record).

**The one invariant:** *a held item and its verification never disagree without you seeing it.*
Every rule below serves that invariant.

## The binding (do this at claim time)

Bind **one** claim-guard `run_id` to the held `item_id`, the moment you claim — but note how the
tool actually behaves (verified against `tool-claim-ledger` source):

- **`start_run` does NOT accept a caller-chosen id.** It always returns a fresh server-issued
  `run_id` (e.g. `run_a1b2c3d4`) and silently discards any id you pass. So **capture the `run_id` it
  returns** and record the `run_id ↔ item_id` pairing yourself — in `SCRATCH.md` or the item's
  design field. That written mapping IS the binding today; there is no name-based binding.
- **Always pass that one captured `run_id` to every `add_claim` / `record_verdict`.** An empty
  `run_id` does not fail safe: on `add_claim` it silently spins up a *brand-new* run, forking your
  claims onto an id you never intended; on `record_verdict` it is rejected outright. Either way the
  fix is the same — reuse the captured id, never an empty one.
- One run per item, for the item's life. If the work splits, split the item; do not fork a second
  run onto one hold.

## The procedure

```
1. work_claim(project, item_id)          # custody established, renews automatically
2. run_id = start_run()["run_id"]        # CAPTURE server-issued id; record run_id↔item_id in SCRATCH
3. …build the change…                    # edit outside the /claim-guard fence
4. gate the change:
     - activate /claim-guard mode (write-fenced) and load `claim-guard-here`
     - harvest → fan-out → debate → gate, all under the captured run_id
5. on BLOCK  → work_declare("awaiting_human"); fix or waive; re-gate. DO NOT resolve.
   on PASS   → work_resolve(id, reason)   # id = the item_id bound in step 1; include verdict + coverage
```

Steps 4 and 5 are the load-bearing ones. The rest is ordinary work-tracker use.

## The five rules (each closes a measured failure)

1. **Gate-before-resolve.** Do not `work_resolve` until the item's bound run has a **PASS** gate.
   *Closes:* items resolved beside an un-gated / BLOCK ledger run.
2. **One captured `run_id`, never empty.** Reuse the server-issued `run_id` from `start_run`; an
   empty `run_id` forks a new run on `add_claim` (and is rejected on `record_verdict`).
   *Closes:* claims forking onto an unintended run — the gate you think you're filling stays empty.
3. **Park legibly.** The instant a gate returns BLOCK, or you are waiting on a human waive, call
   `work_declare("awaiting_human")`. A gate cycle routinely outruns the custody TTL; declaring is
   what makes a long, legitimate hold *legible* rather than silently-long.
   *Closes:* an item held ~48 extra minutes through a BLOCK→waive→re-gate tail with nothing
   signalling why.
4. **Author ≠ waiver.** If you authored a claim, do not also be the sole waiver of its REFUTED
   verdict. Route the harvest through the harvest lenses (`claim-harvester` / `purpose-inquisitor`)
   and surface any waive to a human. A "wording-only" waive is still a waive of the ratchet.
   *Closes:* the same actor authoring all claims and waiving their own REFUTED verdicts while
   holding the blocked item.
5. **REFUTED that isn't wording-only → `work_file` now.** A real REFUTED finding is discovered work;
   file it against the held item immediately, don't carry it in your head.
   *Closes:* gate findings that never became queue items.

## On gate BLOCK

BLOCK is not failure — it is the gate doing its job on a held item. Do, in order:
`work_declare("awaiting_human")` → read every entry in `blocking_claims` (a single claim can appear
twice — once `REFUTED`, once `no-adverse-state-test` — and each is an independent fix) → fix the code
or, only for a genuine claim-authoring defect, waive with a human in the loop → **re-gate** → resolve
only on PASS. The hold is legitimate; rule 3 is what keeps it honest.

## Session-end / hand-off stranded-state checklist

Before ending a session (or handing off), for **every** item you hold, confirm none of these:

- [ ] Held item with **no bound run** started.
- [ ] Bound run with claims but **no gate** ever run.
- [ ] Any `add_claim` / `record_verdict` recorded with an **empty `run_id`**.
- [ ] A gate **in flight** (lenses delegated, no verdict) with the item still held.
- [ ] Latest gate is **BLOCK** but the item is still held and **not** declared `awaiting_human`.

Any box tickable = the two systems disagree. **Stop and reconcile** — resolve, re-gate, `work_file`
the remainder, or `work_release` the item — before the session ends. Do not leave the seam dangling.

## Session-start resume checklist

A session-end checklist does not help the session that never reached its end — a crash, context
exhaustion, or hand-off. **Empirically REFUTED (arm A2, both-store DTU probe):** a fresh session
following this skill literally does a queue-mode `work_claim` and never looks back, so a strand left
by a prior session persists undetected. So **before claiming any NEW work**, for every item the
work-tracker shows **held by your own actor identity** in this project (`work_list --status held`,
filtered to yourself):

- [ ] Load the `run_id ↔ item_id` binding (`SCRATCH.md` / the item's design field) for that item.
- [ ] Apply the session-end checklist's conditions to it *right now*: bound run with claims but no
      gate, empty-`run_id` claims, a gate in flight, or a BLOCK not declared `awaiting_human`.
- [ ] Reconcile before proceeding to anything else — finish the gate, `work_declare`, `work_file` the
      remainder, or `work_release`. Do not silently start other work while a resumable strand sits
      under your own name.

## Multi-driver note

Two sessions on one queue have **no automatic awareness of each other's holds**. Before claiming,
`work_status` / `work_list` the project; coordinate through the item's design field or a doc on disk,
not by pasting one session's output into another. One driver per queue where you can.

## Why a skill and not tool code

The enforcing version — `work_claim` carrying a `run_id`, `work_resolve` refusing on a BLOCK/absent
bound gate, auto-`declare` on BLOCK — is the north-star, but it spans two module repos (one not
ours). This skill is the bridge that works **today** and is itself gate-testable. When the binding
lands in code, this skill becomes its usage guide.

## How this skill's own safety claims are verified

Its behavioral safety claims ("*follow this and the two stores never terminally disagree*") are
**prose-untestable statically** — they live in an agent's conduct across two repos, not in one
function. They are verified empirically, not asserted: a **both-store DTU probe** stands the adverse
state up and a **stranded-state oracle** reads ground truth from *both* stores after the driver
exits, plus an **LLM-as-judge** for the process the oracle can't see (did the discipline actually
run, or did the state just happen to end clean?). See the `probe-patterns` / `adverse-state-catalog`
skills and `FINDINGS-work-tracker-x-claim-guard.md` §8. A behavioral claim is DELIVERED only as a
bounded-rate probe that goes red-on-violation — never as a prose assertion.

## Quick reference

| Moment | Call | Rule |
|---|---|---|
| Claim | `work_claim`, then `start_run` and capture+record its `run_id` | 2 |
| Building | edit outside the fence | — |
| Gate | `/claim-guard` + `claim-guard-here`, under the captured `run_id` | 1 |
| Gate BLOCK | `work_declare("awaiting_human")`, fix/waive, re-gate | 3, 4 |
| Real REFUTED | `work_file` against the item | 5 |
| Gate PASS | `work_resolve` with verdict + coverage in the reason | 1 |
| Session end | run the stranded-state checklist | all |
