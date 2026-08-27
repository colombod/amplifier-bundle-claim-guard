# `tool-claim-ledger` — Interface Contract

**Status:** authoritative interface for the module. The implementation is a separate step; build to
this contract. This is the **trust anchor** of the bundle — it is where the gate's integrity
guarantees are *structural* rather than conventional. If the ledger is correct, the gate is correct;
if the ledger can be argued out of a verdict, so can the gate.

## Module & tool

| | |
|---|---|
| Module dir | `modules/tool-claim-ledger/` |
| Bundle wiring | declared in `behaviors/claim-guard.yaml` → `tools:` with a **pinned git URL** source (`…@main#subdirectory=modules/tool-claim-ledger`), not a relative path — a relative source re-bases onto the declaring file's directory and breaks under registry / `--app` composition |
| Tool name | **`claim_ledger`** — a single tool dispatched by an `operation` parameter (one name to allow-list in the `/claim-guard` mode) |
| Persistence | JSON at `<repo_root>/<run_dir>/<run_id>/ledger.json` (`run_dir` from config, default `.claim-guard`), written **atomically** (temp file + `fsync` + `os.replace`) so a crash mid-write can never corrupt or truncate a run's only durable record |
| Config | `run_dir: str` (default `.claim-guard`); `repo_root: str` (optional — defaults to `Path.cwd()` resolved **once** at tool construction, never re-derived per call — see "Ledger durability" below) |
| Writes | **only** under `<repo_root>/<run_dir>/<run_id>/`. Never elsewhere. This is the only write capability in the gate session. |
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

  "waiver": null,                                            // { "by": "...", "reason": "...", "at": "ISO8601" } | null

  "lens_errors": []                                          // appended by record_lens_error: [{ lens, error, recorded_at }, ...]
                                                               // -- makes gate limb 4 observable; never a verdict, never touches
                                                               // aggregate/adverse_state_test
}
```

### Roster policy (declared once per run — see `declare_roster`)

```json
{
  "mandatory": ["correspondence-auditor"],           // lens names expected on EVERY claim
  "conditional": {
    "chokepoint-mapper": {
      "types": ["safety"],                           // claim types that trigger this lens
      "included": true,                               // true|false -- both required with `reason`
      "reason": "2 claims name a guard/prevention mechanism"
    }
  },
  "declared_by": "concierge | test | null",           // free-form provenance (optional)
  "declared_at": "ISO8601"
}
```

`expected_lenses(claim, roster)` is a **pure, lazy** function of `(claim.type, roster)` — it
is never persisted per claim, so a Gate-A retype of a claim's `type` automatically re-routes
its expected lenses on the very next `aggregate`/`gate`/`render_matrix` call.

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
  "probe_scope": "in-scope|out-of-scope",             // default "in-scope" -- see gate limb 2
  "created_at": "ISO8601",
  "ledger_root": "/abs/path/to/<repo_root>/<run_dir>", // resolved ONCE at run creation
  "ledger_path": "/abs/path/to/.../ledger.json",       // this run's own durable location
  "claims": [ /* Claim records */ ],
  "debate": [ /* Debate-relay records — see record_debate */ ],
  "rejections": [ /* record_verdict rejections — evidence_required/counter_case_required/ratchet_violation */ ],
  "gates": [ /* one entry per `gate` invocation: {at, verdict, gate_policy, blocking_count, coverage} */ ],
  "roster": null,                                      // set by declare_roster; null = undeclared
  "roster_history": []                                 // prior rosters, oldest first, pushed on re-declaration
}
```

**Ledger durability.** `repo_root` is resolved **once**, at `ClaimLedgerTool` construction
time (config-overridable via `repo_root`; defaults to `Path.cwd()` at that moment) — never
re-derived from `Path.cwd()` per `execute()` call. Real runs often execute from an ephemeral
or container cwd (a DTU, `/tmp`); re-deriving `Path.cwd()` per call means the only durable
artifact of a run — including a BLOCK verdict — can die with that cwd, and cross-call cwd
drift can split one run's writes across two different confinement roots. `ledger_root` /
`ledger_path` are computed once at run-creation time from the store's own resolved
confinement root, persisted into the run record itself, and returned by `start_run`, `gate`,
and `report` — so a BLOCK verdict is never presented without also saying where its only
durable record lives.

---

## Operations

All operations take `run_id` (string). `start_run` is the **sole** way to obtain one, and is
the one operation for which `run_id` is *optional* on input (see `start_run` below for its
resume/create/mint semantics). For every other operation, `run_id` must name a run that
already exists: an empty/missing `run_id` on `add_claim` or `add_claims` is rejected loudly
(`invalid_input`), and a non-empty `run_id` naming no existing run is likewise rejected loudly
(`run_not_found`) — neither case is ever silently forked into a fresh, different run. Every
operation returns `{ "ok": true, ... }` or `{ "ok": false, "error": "<code>", "message": "<human>" }`.

**17 ops total.** Thirteen primitives (below, including `declare_roster`), plus four
**concierge ops** — `start_run`, `add_claims`, `report`, `list_runs` — which are thin
compositions of the primitives (`list_runs` is read-only rather than a composition, but is
grouped with the concierge ops for the same reason: it exists purely to make the ledger's
state discoverable without hand-driving the primitives). The concierge ops exist so an
orchestrating agent never invents a `run_id`, never fires one `add_claim` per harvested claim,
and never stitches the verdict together by hand. They add **no** new validation, aggregation, or
gate semantics: each reuses the underlying handler's validation verbatim.

> **Storage is private to this tool.** The on-disk JSON under `<repo_root>/<run_dir>/<run_id>/` is an
> implementation detail. Callers read the ledger via `list_claims` / `report`, never by opening the
> files. Hand-editing the JSON, or reasoning off the raw file, defeats every structural guarantee
> below (evidence enforcement, the ratchet, worst-wins).

### `add_claim`
Add a claim (idempotent on stable `claim_id`; a re-add updates `source`/`basis` but never resets
verdicts).

- **in:** `{ run_id, text, type, source, inferred, basis?, quote? }`
- **out:** `{ ok, claim_id, run_id, was_new }`
- Computes the stable `claim_id` (below). Sets `probe_eligibility` from `type`:
  `safety|quantitative|temporal|concurrency` → `eligible`; `correspondence|coverage` → `not_eligible`.
- **rejects:** `invalid_input` for an empty/missing `run_id` (or missing `text`/`type`/`source`);
  `run_not_found` for a non-empty `run_id` that names no existing run. Neither case creates a
  run — the sanctioned flow is `start_run` (optionally at a caller-chosen id, see below) THEN
  `add_claim`/`add_claims`; there is no auto-create-on-add path.

### `list_claims`
- **in:** `{ run_id, type?, aggregate? }` (optional filters)
- **out:** `{ ok, run_id, claims: [Claim], count }`

### `record_verdict`
Record (or, in a later round, revise) one lens's verdict for one claim. **Enforces the evidence
rules** (below). Recomputes the claim's `aggregate` after writing.

- **in:** `{ run_id, claim_id, lens, verdict, evidence?, counter_case?, adverse_state_test?, round? }`
- **out:** `{ ok, claim_id, lens, verdict, aggregate }` or an `evidence_required` /
  `ratchet_violation` error (rejected, nothing written).

### `record_lens_error`  *(closes the limb-4 blind spot)*
Record that a lens errored/crashed while attempting to verify a claim, so a broken
verification attempt is distinguishable from a claim that simply hasn't been looked
at yet (both would otherwise read as `PENDING`). Appends `{ lens, error, recorded_at }`
to `claim.lens_errors`. **Never** creates a verdict, **never** touches
`verdicts`/`aggregate`, and **never** touches `adverse_state_test` — a lens error is
not a verdict and must never be counted by worst-wins or gate limbs 1–3. Surfaces in
`gate` as a distinct `lens-error:<lens>@<claim_id>` indeterminate reason (limb 4) and
in `render_matrix`'s markdown as a `Lens errors` column entry.

- **in:** `{ run_id, claim_id, lens, error }`
- **out:** `{ ok, claim_id, run_id, lens, lens_error }` or `invalid_input` /
  `run_not_found` / `claim_not_found`

### `declare_roster`  *(closes the silent lens-coverage hole)*
Declare the run-level roster POLICY the gate derives per-claim **expected lenses** from — see
"Roster policy" above and "The gate rule" below. A rostered lens that leaves NO trace (no
verdict, no `record_lens_error`) on a claim it was expected on was previously invisible: the
gate reported full coverage even though a mandatory lens silently skipped a claim.
`declare_roster` closes that hole by making the *expectation* explicit and machine-checkable.

Structurally **rejects (writes nothing)** on any validation failure. On success, **replaces**
the run's `roster` wholesale, pushing any prior roster to `roster_history` (append-only, oldest
first) — re-declaration is a supported, expected operation (e.g. Gate-A adds a claim type
requiring a new conditional lens), not a workaround. **Never** rejects a lens's verdict for
being "off-roster" — that is `record_verdict`'s job to never do (a roster typo must never
discard a real adversarial finding); a mismatch surfaces as `roster-inconsistency` at the gate
instead.

- **in:** `{ run_id, mandatory: [lens, ...], conditional?: { <lens>: { types: [claim_type,...], included: bool, reason: str } }, declared_by? }`
  — `mandatory` MAY be empty (the explicit opt-out, paired with an empty `conditional`, see
  "The empty-roster opt-out" below). Each `conditional` entry requires **both** `included` and
  `reason` whether including or excluding a lens — exclusion is an auditable decision, not a
  silent drop. `types` must be drawn from the known claim-type vocabulary.
- **out (success):** `{ ok, run_id, roster, expected: [ { claim_id, type, expected_lenses: [lens, ...] } ], replaced }`
  — `expected` is the roster echoed back, pre-resolved per **existing** claim in the run (a
  convenience for the caller; `expected_lenses` is still derived lazily by the gate on every
  call, so a later retype/add still re-routes correctly even though this echo is a snapshot).
- **out (rejected):** `{ ok: false, error: "invalid_input", message: "..." }` (unknown claim
  type in `types`, a `conditional` entry missing `included`/`reason`, or a lens name appearing
  in **both** `mandatory` and `conditional`) or `run_not_found`.

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
Compute the gate verdict deterministically (below). Idempotent aside from appending one entry
to the run's `gates` history (see "Gate history" below); never mutates verdicts.

- **in:** `{ run_id, gate_policy? }` (defaults to the run's stored policy)
- **out:**
  ```json
  {
    "ok": true,
    "run_id": "run_...",
    "verdict": "PASS|BLOCK|INDETERMINATE",
    "blocking_claims": [
      { "claim_id", "text", "reasons": ["REFUTED", "no-adverse-state-test"], "category": "substantive|procedural" }
    ],
    "blocking_summary": { "substantive": 1, "procedural": 0, "total_claims_blocked": 1 },
    "indeterminate_reasons": [
      "zero-claims-harvested" | "claim-pending:<claim_id>" | "lens-error:<lens>@<claim_id>" |
      "lens-coverage-gap:<lens>@<claim_id>" | "roster-inconsistency:<lens>@<claim_id>" | "no-roster-declared"
    ],
    "advisory_reasons": [ "unprobed-safety-claim:<claim_id>" ],
    "coverage": {
      "harvested": 12, "verified": 12, "probed": 0, "deferred": 3, "waived": 1,
      "lens_expected": 24, "lens_covered": 22, "advisory": 0
    },
    "ledger_path": "/abs/path/to/.../ledger.json"
  }
  ```
  `blocking_claims` is grouped **one entry per blocked claim** (not per limb) — a claim
  tripping multiple limbs (e.g. REFUTED + no-adverse-state-test) appears exactly once, with
  every tripped reason in `reasons` (limb order) and a `category`: `substantive` if `REFUTED`
  is among the reasons, else `procedural`. Substantive entries sort before procedural ones;
  `blocking_summary` gives the reader the counts without re-scanning the list.
  `lens_expected`/`lens_covered` are `null` (never `0`) when no roster has been declared for
  the run — `0/0` would read as "complete" to a human skimming the coverage line; `null`
  (rendered `n/a` by `render_matrix`) does not.

### `render_matrix`
Render the claim-verification matrix for humans (markdown) or CI (json).

- **in:** `{ run_id, format: "markdown"|"json" }`
- **out:** `{ ok, content }` — markdown table with columns
  `Claim | Type | Source (inferred?) | Verdict | Evidence (file:line) | Counter-case | Adverse-state test | Lens errors | Coverage gap`,
  always followed by the **coverage line**. The `Lens errors` column renders each
  `claim.lens_errors` entry as `<lens>: <error>` (or `-` when none), so a human reading
  the matrix sees a crashed lens directly rather than inferring it from a silent
  `PENDING` row. The `Coverage gap` column renders, per claim, the rostered lenses that left
  no trace (no verdict, no lens error) on that specific claim — `-` when none or when no
  roster is declared. The coverage line reads
  `Coverage: harvested=… verified=… lens_covered=<covered>/<expected> (or "n/a (no roster declared)") probed=… deferred=… waived=… advisory=<n>`
  — `advisory` counts safety claims with no adverse-state test that this run's `probe_scope`
  surfaced as advisory rather than blocking (always `0` under `probe_scope: "in-scope"`). The
  json form is the raw run record (lens errors, roster, `probe_scope` included as-is).

---

## Concierge ops (thin compositions — no new semantics)

These four exist to make the concierge's interaction with the ledger **mechanical and
discoverable**: the run_id comes from the ledger rather than from the agent, a harvested batch
lands in one call, the verdict always ships with the matrix that explains it, and the state of
every run is queryable without hand-driving the primitives. Each reuses an existing handler's
validation verbatim — none adds a rule, and none can be used to bypass one.

### `start_run`
Explicitly create — or resume — a run and return its `run_id`, without adding a claim first —
the **sole** way to obtain a `run_id` (`add_claim`/`add_claims` reject an empty/missing OR
unknown one loudly rather than auto-creating a run). `run_id` is **optional** on input, and its
presence/absence selects one of three behaviors:

1. **omitted/empty** — mint one via `new_run_id()` (unchanged from before this was
   configurable): the sole way to obtain a brand-new, uniquely-named run.
2. **provided, and a run already exists at that id** — **RESUME** it: return the existing
   run's own `run_id`/`gate_policy`/`probe_scope`/`ledger_path` as-is. This never resets or
   overwrites the run's `claims`, `gate_policy`, `probe_scope`, or `roster` — any
   `gate_policy`/`probe_scope` passed on *this* call are ignored, since the run already has its
   own. Lets a recipe/caller re-establish a handle on a run it (or another session) already
   opened, idempotently, without risking a wipe.
3. **provided, and no run exists at that id** — create a new run AT that id, using this call's
   `gate_policy`/`probe_scope`, via the same `_new_run_record()` + `save()` path used for a
   minted id.

A caller-supplied `run_id` is validated with the **same** sanitizer/confinement rules every
other op already applies (`store.load()` resolves it through `sanitize_run_id()` internally,
reused verbatim — not reimplemented): an invalid id raises `WriteConfinementError`, which
surfaces as the tool's existing `write_confinement_violation` error (the same shape any other
op already produces for a malformed/malicious `run_id`); nothing is written.
`validate_gate_policy`/`validate_probe_scope` still reject an unknown policy/scope on the
mint/create-at-id paths (irrelevant, and skipped, on resume).

- **in:** `{ run_id?, gate_policy?, probe_scope? }` — `gate_policy` defaults to
  `blocking-with-waiver`; `probe_scope` defaults to `"in-scope"` (see "The gate rule" below)
- **out:** `{ ok, run_id, gate_policy, probe_scope, ledger_path, resumed }` — `resumed` is
  `true` only for case 2 above
- **rejects:** `invalid_input` — `unknown gate_policy: <value>` or `unknown probe_scope:
  <value>` (mint/create-at-id paths only; nothing written); `write_confinement_violation` for
  an invalid caller-supplied `run_id` (nothing written)

The agent never fabricates or guesses a `run_id` on the mint path; it asks for one — but may
now also pass one explicitly to resume or establish a specific run by id (e.g. one keyed to a
work-tracker item or PR number).

### `add_claims`
Bulk-add a harvested batch, reusing `add_claim`'s validation (and its stable-`claim_id`
idempotency) for **each** element.

- **in:** `{ run_id, claims: [ { text, type, source, inferred, basis?, quote? }, … ] }`
  — `claims` must be a **non-empty array**; `run_id` must name an existing run (see `start_run`)
- **out:** `{ ok, run_id, results: [ { claim_id, was_new } ], added, updated, errors: [ { index, error, message } ] }`
- **rejects (whole call, nothing written, batch never iterated):** `invalid_input` — `claims must
  be a non-empty array`, or an empty/missing `run_id`; `run_not_found` — a non-empty `run_id`
  naming no existing run

Two behaviours worth stating explicitly:

- **`run_id` must already exist — checked ONCE, up front, for the whole batch.** An empty/missing
  `run_id` is `invalid_input`; a non-empty `run_id` naming no existing run is `run_not_found` —
  either way the WHOLE call is rejected before any element is processed (symmetric with
  `add_claim`'s own per-call rejection, and with the `run_not_found` shape `record_verdict`/`gate`
  already use). There is no auto-create path: the sanctioned flow is `start_run` (optionally at a
  caller-chosen id) THEN `add_claims`.
- **A malformed element does NOT abort the batch.** It is recorded in `errors` (with its `index`)
  and the remaining elements still land. One bad element among N valid ones must never drop the
  rest — a silently truncated harvest would read downstream as a smaller, cleaner changeset. This
  is distinct from the run_id check above: an element's own bad shape (e.g. missing `source`) is
  a per-element problem, not a whole-batch one.

### `report`
One-call gate verdict **plus** the rendered matrix. A thin composition of `gate` + `render_matrix`
— it reuses both handlers' validation (missing/unknown `run_id`, invalid `gate_policy`, invalid
`format`) verbatim and reimplements none of it. Equivalent to calling `gate` then `render_matrix`
separately, in one round trip.

- **in:** `{ run_id, gate_policy?, format? }` — `gate_policy` defaults to the run's stored policy;
  `format` defaults to `"markdown"`
- **out:** `{ ok, run_id, verdict, blocking_claims, indeterminate_reasons, coverage, matrix }`
  — the first five fields are `gate`'s output verbatim; `matrix` is `render_matrix`'s `content`
- **rejects:** returns the underlying `gate` error unchanged if gating fails, else the underlying
  `render_matrix` error unchanged. The matrix is never rendered for a run that failed to gate.

Because `report` computes both from the same ledger read, a verdict can never be presented
alongside a matrix from a different state.

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
   with no adverse-state test still BLOCKs (the B-4 case) — **but ONLY when the run's
   `probe_scope` is `"in-scope"`** (the default). A run that declares `probe_scope:
   "out-of-scope"` (a static-only run, e.g. the `verify-claims` MVP, which never gathers dynamic
   adverse-state evidence) never had the mandate to fill this gap, so the limb does not BLOCK it:
   the claim is instead surfaced as an advisory reason `unprobed-safety-claim:<claim_id>` on
   `advisory_reasons`, and never affects the verdict. Waiver behavior is unchanged in **both**
   modes — a waived safety claim clears this limb either way;
3. any claim `aggregate == UNTESTABLE` with no recorded `waiver` — *policy-dependent:* under
   `advisory` this is reported not blocked; under `blocking-with-waiver`/`blocking` it BLOCKs
   (waiver clears it only under `blocking-with-waiver`).

`verdict = INDETERMINATE` (never PASS) if **any**:

4. any claim is `PENDING` (an expected lens result is missing — zero recorded verdicts), reported
   as `claim-pending:<claim_id>`; **or** any lens recorded an error via `record_lens_error`,
   reported as its own `lens-error:<lens>@<claim_id>` — a distinct signal from `claim-pending`, so
   a crashed lens is never conflated with "not yet verified". A claim can carry both reasons at
   once, or a `lens-error` alone even if the claim already has a verdict from another lens (the
   error never touches that claim's `aggregate`);
4c. **(roster coverage, additive — see `declare_roster` and "Roster policy" above)** a rostered
   lens left NO trace (no verdict, no lens error) on a claim it was expected on, reported as
   `lens-coverage-gap:<lens>@<claim_id>`; **or** a lens left a trace on a claim it was NOT
   expected on, reported as `roster-inconsistency:<lens>@<claim_id>` (this is the anti-shrink
   guard — narrowing the roster to hide a gap turns it into an inconsistency instead, never a
   silent pass); **or** the run harvested claims but never declared a roster at all, reported as
   `no-roster-declared` (suppressed when `harvested == 0`, since limb 5 already covers that run —
   an undeclared roster is *unknown* coverage, not full coverage; the **explicit empty roster**
   — `{mandatory: [], conditional: {}}` — is the durable opt-out that suppresses this signal).
   4c never rewrites a claim's `aggregate` or contributes to limbs 1–3 — a coverage gap can only
   ever produce an INDETERMINATE run, never a fabricated BLOCK/PASS/CONFIRMED;
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

- `normalize(text)`: Unicode NFKC + typographic
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
2. **gate limbs** — each independently, plus limb-2-with-CONFIRMED, plus the three
   policy modifiers, plus zero-claims→INDETERMINATE, plus limb-4's two distinct reason shapes
   (`claim-pending:<claim_id>` vs `lens-error:<lens>@<claim_id>`, and a `record_lens_error` call
   that never creates a verdict or moves `aggregate`), plus limb-4c's three roster-coverage
   reason shapes (`lens-coverage-gap`, `roster-inconsistency`, `no-roster-declared`) and the
   empty-roster opt-out, plus limb-2's `probe_scope` conditionality (`in-scope` blocks,
   `out-of-scope` is merely advisory, waiver clears either way).
3. **evidence enforcement** — CONFIRMED/REFUTED without an anchor rejected; REFUTED without a
   counter-case rejected.
4. **evidence ratchet** — REFUTED→CONFIRMED with no new anchor rejected; with a new anchor accepted.
5. **stable IDs** — reword-stable, type-sensitive, run-independent; collision disambiguation.
6. **write confinement** — the tool writes only under `<repo_root>/<run_dir>/<run_id>/`.
7. **atomic save** — a save that fails partway leaves no `.tmp` file and does not corrupt the
   prior complete `ledger.json`; repeated saves leave exactly one final file.
8. **ledger durability** — `start_run`/`gate`/`report` return an absolute `ledger_path` that
   matches `store.ledger_file(run_id)`; `repo_root` resolved once at construction survives cwd
   drift between calls (with or without a `repo_root` config override).

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

**`probe_scope` bridges the MVP/Phase-2 gap honestly.** A run declared `probe_scope:
"out-of-scope"` (e.g. `verify-claims.yaml`, the static-only MVP recipe) never gathers dynamic
adverse-state evidence at all — so gate limb 2 blocking every safety claim without one would be
blocking on an absence the run never had the mandate to fill. Declaring `out-of-scope` downgrades
that gap to an advisory reason (`unprobed-safety-claim:<claim_id>` on `advisory_reasons`) instead
of a block, so the MVP's static verdict is not artificially poisoned by work Phase-2 hasn't run
yet — while still surfacing every such claim for a human to see. A Phase-2-capable run (or any
run that omits `probe_scope`, or sets it explicitly to `"in-scope"`) keeps the original blocking
behavior unchanged.

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
