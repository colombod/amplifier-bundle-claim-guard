# `tool-claim-ledger` — Interface Contract

**Status:** authoritative interface for the module. The implementation is a separate step; build to
this contract. This is the **trust anchor** of the bundle — it is where the gate's integrity
guarantees are *structural* rather than conventional. If the ledger is correct, the gate is correct;
if the ledger can be argued out of a verdict, so can the gate.

## Module & tool

| | |
|---|---|
| Module dir | `modules/tool-claim-ledger/` |
| Bundle wiring | declared in `behaviors/claim-guard.yaml` → `tools:` with `source: ./modules/tool-claim-ledger` |
| Tool name | **`claim_ledger`** — a single tool dispatched by an `operation` parameter (one name to allow-list in the `/claim-guard` mode) |
| Persistence | JSON at `<repo>/<run_dir>/<run_id>/ledger.json` (`run_dir` from config, default `.claim-guard`) |
| Config | `run_dir: str` (default `.claim-guard`) |
| Writes | **only** under `<repo>/<run_dir>/<run_id>/`. Never elsewhere. This is the only write capability in the gate session. |
| Peer deps | `amplifier-core` is a peer dependency — do NOT declare it in `pyproject.toml`; `dependencies = []` |

The tool mounts via the standard module `mount()` contract (must call
`coordinator.mount("tools", tool, name="claim_ledger")`).

---

## Data model

### Claim record

```json
{
  "claim_id": "clm_<8hex>",              // stable across runs — see Stable Claim IDs (F-9)
  "text": "a degraded server will not corrupt data",
  "type": "correspondence|safety|quantitative|temporal|concurrency|coverage",
  "source": "issue:#123 | commit:<sha> | docstring:registry.py:88 | pr-body | council-verdict:<lens/finding>",
  "inferred": true,
  "basis": "one-line derivation (implicit claims only; null for explicit)",
  "quote": "verbatim line the claim came from (explicit claims)",

  "verdicts": [ /* Verdict records, one per lens — see below */ ],

  "aggregate": "REFUTED|UNTESTABLE|CONFIRMED|N/A|PENDING",   // computed, worst-wins
  "adverse_state_test": {                                     // gate limb 2 reads this
    "exists": false,
    "test_ref": "path::test_name | null",
    "reason": "why it does/does not count as an adverse-state test that fails on violation"
  },

  // ---- Phase-2 fields: present in the schema now, filled later; MVP leaves as defaults ----
  "probe_eligibility": "not_eligible|eligible|deferred",     // MVP: derived from type (see below)
  "probe": null,                                             // Phase-2 probe spec + run evidence
  "standing_test": null,                                     // Phase-2 graduated regression test ref

  "waiver": null                                             // { "by": "...", "reason": "...", "at": "ISO8601" } | null
}
```

### Verdict record (one per lens per claim)

```json
{
  "lens": "correspondence-auditor|test-correspondence-auditor|chokepoint-mapper|boundary-adversary|pen-tester",
  "verdict": "CONFIRMED|REFUTED|UNTESTABLE|N/A",
  "evidence": ["registry.py:648", "admin.py:972 — no Field(ge=1)"],   // file:line anchors
  "counter_case": "REFUTED only: the exact input/state/sequence that breaks the claim | null",
  "round": 1,                                                          // debate round the verdict was recorded in
  "recorded_at": "ISO8601"
}
```

### Run record

```json
{
  "run_id": "run_<sha8>",
  "gate_policy": "advisory|blocking-with-waiver|blocking",
  "created_at": "ISO8601",
  "claims": [ /* Claim records */ ],
  "debate": [ /* Debate-relay records — see record_debate */ ]
}
```

---

## Operations

All operations take `run_id` (string). If `run_id` is empty on the first `add_claim`, the tool
derives and returns one (see Stable Claim IDs). Every operation returns
`{ "ok": true, ... }` or `{ "ok": false, "error": "<code>", "message": "<human>" }`.

### `add_claim`
Add a claim (idempotent on stable `claim_id`; a re-add updates `source`/`basis` but never resets
verdicts).

- **in:** `{ run_id, text, type, source, inferred, basis?, quote? }`
- **out:** `{ ok, claim_id, run_id, was_new }`
- Computes the stable `claim_id` (below). Sets `probe_eligibility` from `type`:
  `safety|quantitative|temporal|concurrency` → `eligible`; `correspondence|coverage` → `not_eligible`.

### `list_claims`
- **in:** `{ run_id, type?, aggregate? }` (optional filters)
- **out:** `{ ok, run_id, claims: [Claim], count }`

### `record_verdict`
Record (or, in a later round, revise) one lens's verdict for one claim. **Enforces the evidence
rules** (below). Recomputes the claim's `aggregate` after writing.

- **in:** `{ run_id, claim_id, lens, verdict, evidence?, counter_case?, adverse_state_test?, round? }`
- **out:** `{ ok, claim_id, lens, verdict, aggregate }` or an `evidence_required` /
  `ratchet_violation` error (rejected, nothing written).

### `record_debate`  *(F-6 — auditable relay)*
Persist the verbatim payload relayed to a lens in a debate round, so "verbatim relay, no curation"
is auditable after the fact even though it cannot be structurally prevented.

- **in:** `{ run_id, round, to_lens, relayed_payload, from_lenses: [ "lens" ] }`
- **out:** `{ ok, round, to_lens }`

### `waive`  *(policy-gated human downgrade)*
Record a named human waiver on a claim. Only meaningful under `blocking-with-waiver`.

- **in:** `{ run_id, claim_id, by, reason }`
- **out:** `{ ok, claim_id, waiver }`

### `aggregate`
Recompute (idempotently) every claim's `aggregate` from its verdicts, worst-wins. Returns the matrix
data without a gate decision.

- **in:** `{ run_id }`
- **out:** `{ ok, run_id, claims: [ { claim_id, text, type, aggregate, adverse_state_test } ], coverage }`

### `gate`
Compute the gate verdict deterministically (below). Idempotent; does not mutate verdicts.

- **in:** `{ run_id, gate_policy? }` (defaults to the run's stored policy)
- **out:**
  ```json
  {
    "ok": true,
    "run_id": "run_...",
    "verdict": "PASS|BLOCK|INDETERMINATE",
    "blocking_claims": [ { "claim_id", "text", "reason": "REFUTED|no-adverse-state-test|UNTESTABLE-unwaived" } ],
    "indeterminate_reasons": [ "zero-claims-harvested" | "lens-error:<lens>@<claim_id>" ],
    "coverage": { "harvested": 12, "verified": 12, "probed": 0, "deferred": 3, "waived": 1 }
  }
  ```

### `render_matrix`
Render the claim-verification matrix for humans (markdown) or CI (json).

- **in:** `{ run_id, format: "markdown"|"json" }`
- **out:** `{ ok, content }` — markdown table with columns
  `Claim | Type | Source (inferred?) | Load-bearing code | Verdict | Evidence (file:line) | Counter-case | Adverse-state test`,
  always followed by the **coverage line**. The json form is the raw run record.

---

## Worst-wins aggregation (deterministic — never an LLM)

For a claim, aggregate across its lens verdicts by strict precedence:

```
REFUTED  >  UNTESTABLE  >  CONFIRMED  >  N/A
```

- Any single `REFUTED` → aggregate `REFUTED`. A `CONFIRMED` from another lens **cannot** raise it.
  (This is the S-3 case: correspondence-auditor CONFIRMED + chokepoint-mapper REFUTED → **REFUTED**.)
- No `REFUTED` but any `UNTESTABLE` → `UNTESTABLE`.
- All present verdicts `CONFIRMED` (with ≥1) → `CONFIRMED`.
- Only `N/A` → `N/A`. An abstention never lowers an aggregate.
- **A missing expected lens result is NOT `CONFIRMED` and NOT `N/A`** — it makes the claim
  `PENDING` and feeds `gate` limb 4 (lens error / incomplete → INDETERMINATE). A gap must never
  read as a pass.

## The gate rule (deterministic)

`verdict = BLOCK` if **any**:

1. any claim `aggregate == REFUTED`;
2. any claim with `type == "safety"` (or otherwise carrying an integrity/security obligation) has
   `adverse_state_test.exists == false` — **independent of limb 1**, so a CONFIRMED safety claim
   with no adverse-state test still BLOCKs (the B-4 case);
3. any claim `aggregate == UNTESTABLE` with no recorded `waiver` — *policy-dependent:* under
   `advisory` this is reported not blocked; under `blocking-with-waiver`/`blocking` it BLOCKs
   (waiver clears it only under `blocking-with-waiver`).

`verdict = INDETERMINATE` (never PASS) if **any**:

4. any lens errored / returned no structured verdict, or any claim is `PENDING` (an expected lens
   result is missing) → report the specific `lens@claim_id`;
5. **zero claims harvested** (`coverage.harvested == 0`) → reason `zero-claims-harvested` (the S-8
   rule: an empty claim list is a harvest failure, not a clean bill of health).

Otherwise `verdict = PASS`.

**Policy modifiers:**
- `advisory` — always compute and report; never return `BLOCK` (downgrade BLOCK→report, but keep
  INDETERMINATE as INDETERMINATE — an incomplete run is still not a pass).
- `blocking-with-waiver` *(default)* — BLOCK per above; a `waiver` on a claim clears that claim's
  contribution to limbs 1–3 and surfaces in the matrix.
- `blocking` — BLOCK per above; waivers are recorded but do **not** clear a block.

The gate never averages, never softens, never infers intent. It is pure computation over the ledger.

---

## `file:line` evidence enforcement (structural)

`record_verdict` rejects, and writes nothing, when:

- **`evidence_required`** — `verdict` is `CONFIRMED` or `REFUTED` and `evidence` is empty or contains
  no token matching the anchor shape `‹path›:‹line›` (e.g. `registry.py:648`). A verdict without an
  anchor is not a verdict. (`UNTESTABLE` and `N/A` require a one-line reason in `counter_case`/
  `evidence` but no anchor.)
- **`counter_case_required`** — `verdict == REFUTED` and `counter_case` is empty. A refutation must
  name the input/state/sequence that breaks the claim.

## The evidence ratchet (structural — debate rounds)

When `record_verdict` would **revise** a claim whose current `aggregate` (or this lens's prior
verdict) is `REFUTED`, moving it toward `CONFIRMED`:

- **`ratchet_violation`** — reject unless `evidence` contains at least one anchor **not already
  present** anywhere in that claim's existing verdict evidence. Prose alone, or re-citing the same
  lines, cannot clear a `REFUTED`. (This is the S-9 case: "MERGE is idempotent so it's probably
  fine" with no new `file:line` is rejected, and the prior REFUTED stands.)

The rejection is itself appended to the run's audit trail so a concierge can surface "a lens tried
to clear a REFUTED without new evidence."

---

## Stable claim IDs across runs (F-9)

`claim_id = "clm_" + sha1( normalize(text) + "|" + type + "|" + repo_relpath_of(source) )[:8]`

- `normalize(text)` = lowercased, whitespace-collapsed, trailing punctuation stripped — so trivial
  rewording does not fork identity, but a real change of claim does.
- Deliberately **excludes** `inferred`, `basis`, `quote`, line numbers, and the run — a claim keeps
  its identity across re-runs of an evolving PR, and across explicit↔implicit reclassification.
- Enables iterative PR review: push new commits, re-run, and the ledger diffs verdicts against the
  same `claim_id`s (a previously REFUTED claim flipping to CONFIRMED is visible run-over-run).
- Collision handling: if two genuinely different claims normalize equal, append a `-2` disambiguator
  and record both; never silently merge.

---

## Test-first (the module is the trust anchor — F-5)

Write these before any agent is wired to the tool:

1. **worst-wins** — every precedence pair, especially CONFIRMED+REFUTED→REFUTED and the
   missing-lens→PENDING case.
2. **gate limbs** — each of the five independently, plus limb-2-with-CONFIRMED, plus the three
   policy modifiers, plus zero-claims→INDETERMINATE.
3. **evidence enforcement** — CONFIRMED/REFUTED without an anchor rejected; REFUTED without a
   counter-case rejected.
4. **evidence ratchet** — REFUTED→CONFIRMED with no new anchor rejected; with a new anchor accepted.
5. **stable IDs** — reword-stable, type-sensitive, run-independent; collision disambiguation.
6. **write confinement** — the tool writes only under `<repo>/<run_dir>/<run_id>/`.

---

## Phase-2 readiness (do not build, do not foreclose)

The schema already carries `probe_eligibility`, `probe`, `standing_test`, and the `deferred` state.
Phase 2 (`probe-claims.yaml` + `probe-designer`/`pen-tester`/`regression-graduator`) will:
- add `design_probe`, `record_probe_run`, and `graduate_test` operations;
- set `probe_eligibility: deferred` when an eligible claim is not probed (budget/DTU), which the
  matrix shows as **DEFERRED** — and a deferred **safety** claim still trips gate limb 2
  (deferred ≠ passed);
- fill `adverse_state_test` from a graduated probe (red-before/green-after, 3× deterministic,
  property-level assertion) — the only way a safety claim clears limb 2 by test rather than by
  waiver.

No field added in Phase 2 reshapes an MVP field; the MVP ledger is forward-compatible by construction.
