# Probe P3 spec — session-end stranded state goes undetected

Status: **PROBE SPEC**. Sibling of P2 (`probe-p2-ungated-resolve.md`): P2 is the *resolve-time*
violation ("resolve happened wrongly"); P3 is the *session-end* violation ("the session ended with
the disagreement undetected"). Source: gate safety claim `clm_15bd48c0` + finding G5 (a session
ended holding `ci_473-duw` with claims on an empty `run_id`, no gate, no resolve). Adverse-state
category: **abrupt termination / cross-system disagreement**.

## The forbidden violation

A session ends (or hands off) while **holding an item** whose bound run is in a stranded shape —
**claims but no gate**, or **claims on an empty/forked `run_id`** — and **nothing surfaces the
disagreement**. The two stores silently disagree and no one is told.

## What changed since this finding: the detector now EXISTS

Unlike P2 (whose fix `e9n` is not yet built), P3's **detector was delivered by `d9k`**:
`claim_ledger list_runs(stranded_only=true)` returns every run with claims but not fully verdicted,
plus a `stranded_count`; and (`cgq`) an empty `run_id` can no longer even create the forked-claims
shape (it is rejected at write time). The `claim-guard-here` Phase-7 close-out and the
`work-tracker-with-claim-guard` session-end checklist are the procedural detectors on top. **So P3
is buildable as a GREEN-after regression test today** — it asserts the delivered detector actually
fires.

## Adverse state (stand this up)

- **work-tracker store:** a project with one item, held by the driver, **not resolved**.
- **claim-ledger store:** a run bound to that item with **≥1 harvested claim and no `gate` call**
  (`n5g`: `gated == false`; `d9k`: `stranded == true`). (The historical empty-`run_id` variant is
  now unreachable post-`cgq`; assert that too — see below.)

## Exercise + observation (red-on-violation)

Simulate the session-end checkpoint: run the stranded-state oracle over **both** stores.

```
strays = claim_ledger list_runs(stranded_only=true)      # d9k
assert strays["stranded_count"] >= 1                      # the strand IS surfaced
assert bound_run_id in {r["run_id"] for r in strays["runs"]}
assert any r for that run has gated == false              # n5g: never gated
# and the held-item side:
assert item is still held AND not resolved               # the disagreement is real, not benign
# empty-run_id variant is structurally prevented:
assert op_add_claim(run_id="") -> ok == False             # cgq: cannot create the forked shape
```

- **Detector present (post-d9k):** the assertions PASS — the strand is surfaced, GREEN. The probe
  proves `list_runs(stranded_only)` + the Phase-7 checklist actually catch the G5 shape.
- **Detector removed/regressed (counterfactual RED):** if `list_runs` stopped reporting `stranded`,
  or `stranded_count` dropped the ungated run, the assertion goes RED. That is the property the test
  guards.

## Graduation criteria

Per `properly-delivered-claim`: asserts the property (the strand is surfaced), **RED-before** the
`d9k`/`cgq` mechanisms existed (it could not have passed then — the detector was absent), **GREEN-after**
today, deterministic ≥3×. Because the detector shipped, **P3 can graduate now** as a standing
regression test guarding `list_runs`' stranded semantics and `cgq`'s empty-run_id rejection — unlike
P2, which must wait for `e9n`.

## Relationship to other items

- **`d9k`** — delivered the `list_runs` stranded detector this probe asserts.
- **`cgq`** — closed the empty-`run_id` forked-claims variant at write time.
- **`n5g`** — the `gated`/`last_verdict` fields the oracle reads.
- **Tier-2 #6 / combined-skill session-end checklist** — the procedural detector this probe promotes
  from "manual checklist" toward "standing test".
- **P2 (`6yp`)** — the resolve-time sibling.
