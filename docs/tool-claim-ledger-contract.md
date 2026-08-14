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

  // ---- Phase-2 fields: schema present from MVP; ops below now fill them ----
  "probe_eligibility": "not_eligible|eligible|deferred",     // derived from type at add_claim; deferred set by defer_claim
  "probe": null,                                             // set by record_probe: { designed_by, adverse_state, outcome, evidence, artifacts_path, recorded_at } | null
  "standing_test": null,                                     // set by graduate_test: { path, asserts_property, red_before, green_after, deterministic_runs, recorded_at } | null

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

### `record_probe`  *(Phase-2)*
Attach a probe result to a claim. Writes `claim.probe` **only** — never touches
`verdicts`/`aggregate` (a probe's `FALSIFIED` outcome still requires a separate
`record_verdict` call to actually refute the claim) and never touches
`adverse_state_test`, even on `outcome: SURVIVED`. A survived-but-ungraduated probe
does not clear gate limb 2 — only `graduate_test` can do that.

- **in:** `{ run_id, claim_id, probe: { designed_by, adverse_state, outcome, evidence?, artifacts_path? } }`
  — `outcome` ∈ `FALSIFIED|SURVIVED|UNBUILDABLE`
- **out:** `{ ok, claim_id, run_id, probe }` or `invalid_probe_outcome` /
  `invalid_input` / `run_not_found` / `claim_not_found`

### `defer_claim`  *(Phase-2)*
Mark a probe-eligible claim as `deferred` (probe not run this pass, e.g. budget/DTU
unavailable). Sets `probe_eligibility: "deferred"` — coverage's `deferred` counter and
`render_matrix` read this directly. **Never** sets `adverse_state_test`: a deferred
safety claim still trips gate limb 2 (deferred ≠ passed). Rejected for a claim whose
`probe_eligibility` is `not_eligible`.

- **in:** `{ run_id, claim_id, reason }`
- **out:** `{ ok, claim_id, run_id, probe_eligibility: "deferred" }` or `not_probe_eligible` /
  `invalid_input` / `run_not_found` / `claim_not_found`

### `graduate_test`  *(Phase-2)*
Record that a surviving probe became a standing regression test. **Structurally
rejects (writes nothing)** unless *all* of `asserts_property`, `red_before`,
`green_after` are truthy and `deterministic_runs >= 3`. On success, sets
`claim.standing_test` **and** `claim.adverse_state_test.exists = true` — this is the
only Phase-2 path (besides `record_verdict`'s own `adverse_state_test` update) that
clears gate limb 2 for a claim.

- **in:** `{ run_id, claim_id, standing_test: { path, asserts_property, red_before, green_after, deterministic_runs } }`
- **out (success):** `{ ok, claim_id, run_id, standing_test, adverse_state_test }`
- **out (rejected):** `{ ok: false, error: "graduation_criteria_unmet", message: "...missing: <criteria>" }`
  — nothing written; `claim.standing_test` stays `null` and `adverse_state_test` is
  unchanged.

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

- `normalize(text)` (KI-1 hardening, design/ki1-determinism-spec.md §2): Unicode NFKC + typographic
  quote folding, then segmented into **code-spans** (backtick-delimited, `file.ext[:line]`,
  `snake_case`/`camelCase` identifiers, numbers — preserved atomically, casefolded, with a
  text-embedded `file:line` trailing line number stripped) and **prose-spans** (casefolded,
  a closed contraction map expanded, punctuation folded to whitespace, a small closed set of
  filler words/phrases removed — articles, copula/aux, and boilerplate lead-ins like
  "the code ensures that"). Negation, modals, quantifiers, and numbers are **never** stripped —
  over-collapsing two distinct claims into one id is the primary risk (an `identity_key` match is
  treated as an idempotent re-add by `op_add_claim`, so a false merge silently drops a claim).
  No token sorting, no stemming, no synonym mapping — trivial rewording (case, spacing, unicode
  quote variants, articles, contractions, identifier case, internal punctuation) does not fork
  identity, but a real change of claim does.
- **Id-space shift:** the hardened normalizer computes different `claim_id`s than the prior
  (lowercase + trailing-punctuation-only) normalizer for any text containing internal punctuation,
  articles, or filler boilerplate. A pre-hardening ledger will not diff cleanly against a
  post-hardening run — acceptable, since evaluation ledgers are uncommitted and disposable, and F-9
  diffing is forward-looking from this normalizer onward.
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

## Phase-2 readiness: ledger ops implemented, dynamic probing not yet wired

The ledger-level Phase-2 slice is **implemented**: `record_probe`, `defer_claim`, and
`graduate_test` (above) fill `probe`, `probe_eligibility: deferred`, and `standing_test` /
`adverse_state_test` honestly, and `compute_coverage`'s `probed`/`deferred` counters (read by
both `gate` and `render_matrix`) reflect real data written by these ops rather than always
reading zero.

**What this closes:** before these ops existed, nothing ever wrote `probe`, `standing_test`, or
`probe_eligibility: deferred` — so `coverage.probed`/`coverage.deferred` always read `0` even
once probing existed conceptually. The matrix and gate coverage line are now honest.

**What is still NOT built** (the dynamic half — recipe/agent wiring, not the ledger):
- `probe-claims.yaml` recipe and the `probe-designer`/`pen-tester`/`regression-graduator` agents
  that actually *design and run* probes against an isolated adverse-state environment (DTU) and
  call these ops with real results.
- Any DTU integration. `record_probe`/`graduate_test` are pure ledger writes; they trust whatever
  `probe`/`standing_test` payload the caller provides. Verifying that a payload reflects a real
  DTU run (not a fabricated one) is the calling agent's responsibility, not the ledger's — the
  same trust boundary `record_verdict`'s evidence-anchor enforcement establishes for lens verdicts.

No field or op added in this slice reshapes an MVP field or op; the ledger remains
forward-compatible by construction.
