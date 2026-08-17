# amplifier-bundle-claim-guard

**An adversarial claim-verification gate for Amplifier — layered onto your sessions as a review
gate.** For every claim a changeset makes, claim-guard locates the load-bearing code and tries to
**prove the claim FALSE against the actual shipped source**, emits an auditable
**claim-verification matrix**, and returns a **BLOCK / PASS / INDETERMINATE** verdict.

The operating question flips from *"does it work?"* to ***"how is this claim false?"*** The commit
message is a **hypothesis to disprove**, not a fact.

**The gate rule** (computed deterministically by the `claim_ledger` tool, never by an LLM) —
merge is **BLOCKed** if any of:
1. any claim aggregates to **REFUTED**;
2. any **safety** claim has **no adverse-state test that fails on violation**;
3. any claim aggregates to **UNTESTABLE** with no recorded human waiver;
4. any lens errored / returned no structured verdict → **INDETERMINATE** (never PASS);
5. **zero claims harvested** → **INDETERMINATE** (an empty claim list is a harvest failure, not a
   clean bill of health).

Aggregation across lenses for one claim is **worst-wins**:
`REFUTED > UNTESTABLE > CONFIRMED > N/A`.

It is the missing **implementation-layer** gate — the one that reads shipped code adversarially
against its own claims. Distinct from, and complementary to:

| Gate | Reasons about | Runs |
|---|---|---|
| Design council (`/council`) | intended mechanism, in prose | before code |
| Code review | "does this look correct" | after code, confirmatory |
| Happy-path E2E | success paths you thought of | after code, liveness |
| **claim-guard** | **claim ↔ shipped-code correspondence** | **after build, before merge** |

### When to use this

Run claim-guard as a **pre-merge review gate over a changeset** — a diff or a PR (`base..head`), with
its commit messages and any linked design doc. **Not per-commit:** it reasons about the claims a whole
change makes, so a single commit mid-branch is usually the wrong unit.

It is **invoked deliberately**, not automatically: ask the session to run the gate conversationally,
run the `verify-claims` recipe, or use the `/claim-guard` slash-skill (full install). Wire it as a
**manual pre-merge check** — the point in your flow where you'd otherwise say *"this looks right, ship
it."* See **[Usage](#usage--run-the-gate-on-a-changeset)** for the three inputs it needs.

> **Status: two phases, both built and both exercised end-to-end.**
> **Phase 1 — the static gate (`verify-claims`)** is proven end-to-end against a real regression PR
> (see *What a real run produces* below), and **re-validated at current `HEAD`** after the harvester
> rewrite (`docs/EVALUATION.md` §10 — still `BLOCK`, all four blockers caught).
> **Phase 2 — the dynamic behavioural pen-testing bench (`probe-claims`)** has been run end-to-end in
> a Digital Twin across **both** outcome branches: a **FALSIFIED** probe that empirically **REFUTED**
> a safety claim, and a **SURVIVED** probe **graduated into a standing regression test** that clears
> gate limb 2 (`docs/EVALUATION.md` §8.2–§8.3). **And the fidelity of those runs is now confirmed
> against a real engine:** the core B-1 corruption claim was re-probed against a **live Neo4j** using
> the verbatim production `MERGE` query — degraded (no `:Node` uniqueness constraint) produced
> duplicate `:Node` rows (25/25 rounds, max 8) while the control (constraint present) never exceeded
> 1, **reproducing** the in-process result and confirming the lighter models were faithful proxies
> (`docs/EVALUATION.md` §8.4).
> The two phases are joined only by the shared ledger, so Phase 2 composes onto any completed static
> run. See the **Two phases** section below and `docs/KNOWN_ISSUES.md` (KI-2).

---

## Two phases: static gate + dynamic pen-testing

claim-guard runs as **two phases joined only by a shared ledger** — not by code coupling. Phase 2
reads the ledger Phase 1 wrote (by `run_id`) and composes onto **any** completed static run.

| | **Phase 1 — `verify-claims`** (static gate) | **Phase 2 — `probe-claims`** (dynamic pen-testing) |
|---|---|---|
| Question | *"Does the shipped code do what the claim says?"* | *"Can I make the forbidden thing actually happen?"* |
| Method | read the source adversarially; refute against `file:line` | stand the adverse state up in a **Digital Twin** and attack it |
| Bench | 6 static lenses (harvest pair + 2 core + 2 conditional) | 3 dynamic agents (`probe-designer`, `pen-tester`, `regression-graduator`) |
| Verdicts | `CONFIRMED / REFUTED / UNTESTABLE` (+ deterministic gate) | empirical `REFUTED` (new defect) or a **graduated standing test** |
| Needs | any session (LSP for the chokepoint lens) | a **DTU-capable environment** (Incus/Docker) |
| Terminates | at Gate B ("proceed to dynamic probing?") | at the final re-gate over the enriched ledger |
| Status | **proven end-to-end** on a real PR, **re-validated at `HEAD`** (§10) | **run end-to-end in a twin across both outcome branches** (FALSIFIED→REFUTED, SURVIVED→graduated), **and confirmed against a live Neo4j** (§8.4) |

**The ledger is the seam.** `verify-claims` produces `.claim-guard/<run_id>/ledger.json`;
`probe-claims` takes that same `run_id`, probes the claims whose *type* requires behavioural proof,
and writes the empirical results back to the same ledger. There is no other connection between the
two recipes — deleting Phase 2 leaves Phase 1 completely intact, and Phase 2 can be run days later on
a static run that already finished.

See **[Phase 2 — dynamic behavioural pen-testing](#phase-2--dynamic-behavioural-pen-testing-probe-claims)**
below for the bench, the eligibility rule, graduation, and the Phase-2 install.

---

## Install

claim-guard is meant to ride **on top of** the bundle you already run, as a review gate available
in every session — not as a standalone root bundle you switch to. So the recommended install
layers just the **capability** (the tool + the lens bench + awareness) onto every session via an
**app bundle**.

### ✅ Recommended (lightweight): layer the behavior with `--app`

```bash
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main#subdirectory=behaviors/claim-guard.yaml" --app
```

This registers the **behavior** (`claim-guard-behavior`) as an app bundle, so it is
auto-composed onto **every** session regardless of which primary bundle (`-B ...`) you use. You get:

- the six adversarial **lens agents** (`claim-guard:*`), delegatable from any session;
- the **`claim_ledger`** tool (deterministic aggregation + the gate rule);
- the **awareness context** telling the session the gate exists and how to drive it.

**Verify it layered in** (any base bundle you actually have works — here `foundation`, which
ships by default; substitute whichever primary bundle you run):

```bash
amplifier run -B foundation --mode single \
  "List any sub-agents named claim-guard:* you can delegate to, and whether the claim_ledger tool is available. Do not read code."
```

Real output from this exact command (app-composed onto a plain `-B foundation` session):

```
 claim-guard:boundary-adversary         Finds the input value that inverts a cap/limit/threshold invariant
 claim-guard:chokepoint-mapper          Enumerates every path into a guarded mechanism (LSP incomingCalls)
 claim-guard:claim-harvester            Extracts the explicit claims a change makes
 claim-guard:correspondence-auditor     Mandatory static refutation — prove a claim false against source
 claim-guard:purpose-inquisitor         Infers the implicit claims (what the change exists FOR)
 claim-guard:test-correspondence-audi…  Demands a test that goes RED when the claimed property is violated

That's 6 agents — the harvest pair, the static core, and the conditional lenses.

claim_ledger tool: ✅ available (add_claim, list_claims, record_verdict, …, gate, render_matrix).
```

> You may see `⚠ Could not resolve provider module … — skipping plaintext-secret scan` warnings
> during `bundle add`; they're harmless (the scan is skipped) and the add still succeeds.

**Driving the gate under the lightweight install:** there is no `/claim-guard` slash-skill or
`/claim-guard` mode in this install (those live at the bundle root — see the breakdown below). You
drive the gate **conversationally** — ask the session to run it, e.g.:

> *"Run the claim-guard gate on `git diff main...HEAD` (here are the commit messages and the linked
> design doc). Harvest explicit + implicit claims, fan the lenses out cold, aggregate with
> `claim_ledger`, and give me the matrix + BLOCK/PASS verdict."*

The awareness context + the six lens agents + the `claim_ledger` tool are enough for the session
to orchestrate the full gate this way. See **Usage** below for a worked run.

### Full install: also get the `/claim-guard` mode, playbook skill, and recipe

The one-command `/claim-guard` slash-skill (the polished concierge playbook), the `/claim-guard`
**mode** (which structurally blocks `write_file`/`edit_file` so the gate can't edit the code it
reviews), and the staged `verify-claims` **recipe** live at the **bundle root**, not in the
behavior. To get them, install the whole bundle:

```bash
# Use it as a primary bundle for a review session:
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main"
amplifier run -B claim-guard "/claim-guard git diff main...HEAD"

# …or layer the FULL bundle (mode + skill + recipe + lenses) onto every session:
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main" --app
```

### What each install gives you

| Capability | `--app` **behavior** (recommended) | Full **bundle** (`-B claim-guard` or `--app` root) |
|---|:---:|:---:|
| 6 lens agents (`claim-guard:*`) | ✅ | ✅ |
| `claim_ledger` tool (deterministic gate) | ✅ | ✅ |
| awareness context (gate exists + how) | ✅ | ✅ |
| `/claim-guard` **mode** (blocks file edits) | ❌ | ✅ |
| `/claim-guard` **playbook skill** (one-command concierge) | ❌ | ✅ |
| 5 discipline skills (harvesting, verify-against-source, …) | ❌ | ✅ |
| `verify-claims` **recipe** (staged pipeline + Gate A/B) | ❌ | ✅ |
| How you drive it | ask the session: *"run the claim-guard gate on this diff"* | `/claim-guard <changeset>`, or run the recipe; `/claim-guard` mode for edit-blocking |

**Why the recommended path is the behavior:** a gate you carry into every session — whatever
primary bundle you're running — is exactly the "team-wide behavior" `--app` exists for. You keep
your normal workflow and gain the lenses on demand. Reach for the full bundle when you want the
turnkey `/claim-guard` command, the write-blocking review posture, or the staged recipe with its
human approval gates.

---

## Usage — run the gate on a changeset

Give the gate three things about the revision under review:

1. **the shipped source tree** at that revision (a worktree/checkout — the code actually reviewed);
2. **the diff** for the changeset (`base..head`);
3. **the commit messages** for that range (a primary claim source).

Then the concierge **harvests** explicit + implicit claims, **fans the lens bench out cold**,
**debates** to consensus (one verbatim-relay round when lenses conflict), **aggregates** via
`claim_ledger`, and emits a **claim-verification matrix** + a **BLOCK / PASS / INDETERMINATE**
verdict — every CONFIRMED/REFUTED carrying a `file:line` anchor, every REFUTED a counter-case.

### Lightweight install (conversational)

```bash
# Prepare the inputs (generic placeholders — substitute your repo/range):
git -C /path/to/repo worktree add /tmp/review-worktree <HEAD_SHA>
git -C /path/to/repo diff <BASE_SHA>..<HEAD_SHA> > /tmp/change.diff
git -C /path/to/repo log <BASE_SHA>..<HEAD_SHA> > /tmp/commits.txt
```

Then, in any session (the behavior is app-composed), ask:

> *"Run the claim-guard gate. Source under review: `/tmp/review-worktree`. Diff: `/tmp/change.diff`.
> Commit messages: `/tmp/commits.txt`. Harvest explicit + implicit claims (UNION), fan the six
> lenses out cold, run one debate round on any conflict, then call `claim_ledger` to aggregate and
> gate. Give me the matrix and the verdict with `file:line` evidence. Do not edit any code."*

### Full install (recipe or slash-skill)

```text
# One-command concierge:
/claim-guard <BASE_SHA>..<HEAD_SHA>    (with the worktree, diff, and commits to hand)

# …or the staged pipeline (pauses at Gate A to review harvested claims, Gate B at the MVP boundary):
execute claim-guard:recipes/verify-claims.yaml with:
  changeset:       "<BASE_SHA>..<HEAD_SHA>"
  commit_messages: "<git log text>"
  design_docs:     "<paths or inline text of linked design/spec docs>"
  council_verdict: "<optional: a prior /council verdict to fold in as claims>"
  repo_path:       "<path to the worktree under review>"
  gate_policy:     "blocking-with-waiver"   # advisory | blocking-with-waiver | blocking
  max_rounds:      3
```

### What a real run produces

This gate was accepted against a real regression PR (a context-intelligence server change that a
human reviewer had found four blockers in). Reconstructed to its **pre-remediation** state and run
through the gate, it returned:

```
VERDICT: BLOCK   (policy: blocking-with-waiver)
Coverage: harvested 18 / verified 18 / probed 0 / deferred 0 / waived 0
Aggregates (worst-wins): REFUTED 10, UNTESTABLE 1, CONFIRMED 7
Gate limbs fired: limb 1 (any REFUTED) + limb 2 (safety claim with no adverse-state test)
```

All four known blockers were flagged **REFUTED** with concrete `file:line` evidence and a
counter-case — for example:

| Incident blocker | Verdict | Caught by | Evidence (illustrative) |
|---|---|---|---|
| **B-1** degraded boot corrupts data (`survivable ≠ safe`) | REFUTED | purpose-inquisitor (implicit safety claim) + correspondence-auditor + chokepoint-mapper | no write path reads `schema_health` before MERGE (`neo4j_store.py`, `registry.py`) |
| **B-2** phantom cursor "one branch over" | REFUTED | chokepoint-mapper (correspondence-auditor conceded in round 2) | guard only in `_handle_exhausted_batch`; the common transient-retry loop is unguarded |
| **B-3** `max_delete` cap inversion | REFUTED | boundary-adversary | no `Field(ge=1)`; `max_delete=-1` → `candidates[:-1]` deletes N-1 |
| **B-4** tests certified the wrong thing | REFUTED | test-correspondence-auditor | two fixed-fault fixtures assert liveness, not the claimed universal integrity property |

As a **control**, the same gate run against the **fixed** head flips those claims to CONFIRMED.
The methodology to reproduce this is in [`docs/EVALUATION.md`](docs/EVALUATION.md).

---

## How to read the output

A run produces two things: a **claim-verification matrix** (one row per claim) and a **gate verdict**.
Both are computed by the `claim_ledger` tool — deterministic arithmetic over the ledger, never an LLM
judgement. The full interface is in
[`docs/tool-claim-ledger-contract.md`](docs/tool-claim-ledger-contract.md).

### The gate verdict

| Verdict | Meaning |
|---|---|
| **BLOCK** | at least one gate limb fired — do not merge |
| **INDETERMINATE** | the run is **incomplete or broken**, so no pass can be claimed |
| **PASS** | every claim verified, no limb fired |

**The gate never passes on doubt.** An incomplete run is `INDETERMINATE`, never `PASS` — a gap must
never read as a green light. The limbs, at a glance:

- **limb 1** — any claim aggregates to **REFUTED** → `BLOCK`
- **limb 2** — any **safety** claim has **no adverse-state test** (`adverse_state_test.exists=false`)
  → `BLOCK`, *independently of limb 1* (so a CONFIRMED safety claim with no adverse-state test still
  blocks — the B-4 case). A **deferred** probe does not clear this: deferred ≠ passed.
- **limb 3** — any claim aggregates to **UNTESTABLE** with no recorded human waiver → `BLOCK`
- **limb 4** — any claim is **PENDING**, or any lens recorded an error → `INDETERMINATE`
  (reasons `claim-pending:<claim_id>` and `lens-error:<lens>@<claim_id>`)
- **limb 5** — **zero claims harvested** → `INDETERMINATE` (reason `zero-claims-harvested`) — an empty
  claim list is a harvest failure, not a clean bill of health

`gate_policy` modulates limbs 1–3 only: `advisory` reports instead of blocking; `blocking-with-waiver`
(default) lets a recorded waiver clear a claim; `blocking` records waivers but they clear nothing.
**`INDETERMINATE` is never downgraded by any policy.**

### Per-claim verdict states

Each claim's **aggregate** is computed across its lens verdicts by strict **worst-wins** precedence —
`REFUTED > UNTESTABLE > CONFIRMED > N/A`. One lens's `CONFIRMED` can never raise another's `REFUTED`.

| State | Means |
|---|---|
| **CONFIRMED** | every lens that ruled found the shipped code does what the claim says — each with a `file:line` anchor |
| **REFUTED** | at least one lens proved the claim false, with a `file:line` anchor **and** a counter-case (the input/state/sequence that breaks it) |
| **UNTESTABLE** | a lens could not decide the claim from the available evidence — needs a human call, not a silent pass |
| **PENDING** | **no lens verdict was recorded at all** — the claim was never actually ruled on. Not a pass; feeds limb 4 |
| **N/A** | a lens legitimately abstained (the claim is outside its remit). An abstention never lowers an aggregate |

### Lens errors (a distinct signal from PENDING)

If a lens crashes or returns no structured verdict, that is recorded explicitly via `record_lens_error`
and surfaces as its own `lens-error:<lens>@<claim_id>` reason (limb 4) plus a `Lens errors` column
entry. This exists so **a broken verification is never mistaken for "not looked at yet"** — both would
otherwise read as a silent `PENDING`. A lens error never touches the claim's `aggregate`, and a claim
can carry a lens error even when another lens has already ruled.

### The claim-verification matrix

`render_matrix` emits eight columns, always followed by a coverage line
(`harvested / verified / probed / deferred / waived`):

| Column | Contents |
|---|---|
| **Claim** | the claim text as harvested |
| **Type** | `safety` · `quantitative` · `temporal` · `concurrency` · `correspondence` · `coverage` — this drives probe eligibility |
| **Source (inferred?)** | where the claim came from, and whether it was *inferred* (implicit) rather than stated |
| **Verdict** | the worst-wins aggregate (table above) |
| **Evidence (file:line)** | the anchors every CONFIRMED/REFUTED must carry — structurally enforced |
| **Counter-case** | for a REFUTED claim, the input/state/sequence that breaks it |
| **Adverse-state test** | `yes`/`no` — whether a test exists that goes **red on violation** (this is what limb 2 reads) |
| **Lens errors** | `<lens>: <error>` per recorded error, or `-` |

### One nuance worth knowing: a graduated survivor stays `PENDING`

If a Phase-2 probe **survives** and is **graduated** into a standing regression test, you will see the
claim with `Adverse-state test = yes` but **`Verdict = PENDING`**. That looks wrong. It isn't.

`graduate_test` sets `adverse_state_test.exists = true` — clearing gate limb 2 — but it **deliberately
never fabricates a lens verdict**. A standing test proves the adverse-state property holds; it does not
constitute a lens having *ruled on the claim*. The tool refuses to manufacture a `CONFIRMED` nobody
produced. So a good Phase-2 result reads as *"limb 2 cleared, verdict still owed"* — to move that claim
to `CONFIRMED`, a lens must record an actual verdict. (Worked example: `clm_c39773b8` in
`docs/EVALUATION.md` §8.3.2.)

---

## The bench (MVP)

**Harvesters** (cold, independent, UNIONed — inference can only *add* claims, never remove one)
- **`claim-harvester`** — *"What does this change explicitly say it does?"*
- **`purpose-inquisitor`** — *"What does this change exist FOR, and what does that silently promise?"*

**Mandatory core** (runs on every claim)
- **`correspondence-auditor`** — *"Does the load-bearing code actually do what the claim says — and where is the line that proves it?"*
- **`test-correspondence-auditor`** — *"Is there a test that goes RED when this property is violated, in the adverse state?"*

**Conditional lenses** (triggered by claim type; exclusion recorded with a reason)
- **`chokepoint-mapper`** — *"Which paths into this mechanism are NOT guarded?"* (the "one branch over" catcher; uses LSP `incomingCalls`)
- **`boundary-adversary`** — *"What input value inverts this invariant?"*

The orchestration is **council-shaped**: a concierge fans the bench out cold, runs a
**debate-to-consensus** loop (verbatim relay, no curation), and synthesizes a verdict **with
recorded dissent** plus a roster manifest — mirroring `amplifier-bundle-council`. An optional input
feeds a prior **design-council verdict** in as claims (every addressed `FAIL`/`CONCERN` becomes a
claim to verify against the shipped code).

## Composition

```
amplifier-bundle-claim-guard/
├── bundle.md                              # thin STATIC standalone (foundation, modes, recipes, lsp, own behavior)
├── bundles/with-probing.yaml              # PHASE-2 standalone: static + dynamic behaviors + DTU/parallax/tester
├── behaviors/
│   ├── claim-guard.yaml                   # STATIC capability: tool + 6 agents + awareness (this is what --app installs)
│   └── claim-guard-probing.yaml           # PHASE-2 capability: tool + 3 dynamic agents
├── agents/                                # 6 static-bench + 3 dynamic-bench agents
│   ├── claim-harvester.md                 # static
│   ├── purpose-inquisitor.md              # static
│   ├── correspondence-auditor.md          # static
│   ├── test-correspondence-auditor.md     # static
│   ├── chokepoint-mapper.md               # static
│   ├── boundary-adversary.md              # static
│   ├── probe-designer.md                  # Phase 2
│   ├── pen-tester.md                      # Phase 2
│   └── regression-graduator.md            # Phase 2
├── context/claim-guard-awareness.md       # thin awareness pointer (~250 tokens)
├── modes/claim-guard.md                   # review posture — blocks write_file/edit_file (root-only)
├── skills/                                # concierge playbook + 5 discipline skills (root-only)
│   ├── claim-guard/                        # user-invocable: the concierge playbook
│   ├── claim-harvesting/
│   ├── verify-against-source/
│   ├── adverse-state-catalog/
│   ├── properly-delivered-claim/
│   └── probe-patterns/                     # Phase 2: per-claim-type probe design discipline
├── recipes/
│   ├── verify-claims.yaml                 # Phase 1: the staged static pipeline (root-only)
│   └── probe-claims.yaml                  # Phase 2: dynamic pen-testing pipeline, consumes the ledger by run_id
├── modules/tool-claim-ledger/             # the deterministic ledger + gate (the trust anchor; static + Phase-2 ops)
└── docs/
    ├── tool-claim-ledger-contract.md       # authoritative interface contract for the module
    ├── EVALUATION.md                        # acceptance methodology, Phase-2 (DTU) runs, at-HEAD re-validation
    └── KNOWN_ISSUES.md                      # KI-1 harvest reproducibility (closed at revised bar), KI-2 Phase-2 (closed)
```

The **`tool-claim-ledger`** Python module is the trust anchor: worst-wins aggregation, `file:line`
evidence enforcement, the gate rule, and stable claim IDs across runs. Its interface is specified
in `docs/tool-claim-ledger-contract.md`.

## Phase 2 — dynamic behavioural pen-testing (`probe-claims`)

Static reading proves a *gate is absent*; only **execution** proves a protection is real. Phase 2
takes the claims a static run marked as needing behavioural proof, stands their **adverse state** up
in an isolated **Digital Twin**, and actively attacks it — observing for the **specific forbidden
violation** (corruption / loss / inversion / staleness), never for liveness.

### The dynamic bench

- **`probe-designer`** — *"What experiment, in what adverse state, would falsify this claim?"* Designs
  the probe (adverse-state setup + exercise + the red-on-violation assertion). Does not run it.
- **`pen-tester`** — *"Can I make the forbidden thing actually happen?"* Stands the adverse state up in
  a DTU (delegating to `digital-twin-universe` and `parallax-discovery:antagonist` for
  execution-based falsification), attacks it, and records the empirical outcome. A violation ⇒ an
  empirical **REFUTED** (a *new* defect beyond static reading).
- **`regression-graduator`** — *"Does this surviving probe deserve to become a standing test?"* Applies
  the graduation rule and, only on a pass, promotes the probe to a committed regression test.

### Probe eligibility — by claim TYPE

Eligibility is decided by the claim's type, not by taste (the `claim_ledger` sets it at
`add_claim` time):

| Claim type | Static gate | Needs a behavioural probe? |
|---|---|:---:|
| `safety` ("X cannot happen") | proves a gate is *absent* | **yes** — presence of real protection is only proven by attack |
| `quantitative` ("stays under N") | reading accepts wrong estimates | **yes** |
| `temporal` ("self-clears / re-probes") | a single snapshot can't catch a latch | **yes** (three-phase: observe → repair → observe again) |
| `concurrency` ("no dup under retry/race") | the bug lives in the interleaving | **yes** |
| `correspondence` ("the code does X") | sufficient | no — static-sufficient |
| `coverage` ("this is tested") | sufficient | no — static-sufficient |

A probe-eligible claim that is **not** probed this pass (budget exhausted, DTU unavailable) is marked
**deferred** — and **deferred ≠ passed**: a deferred *safety* claim still trips gate limb 2.

### The graduation rule (structurally gated)

A surviving probe becomes a standing regression test **only if all of**:

1. **red-before** — it fails on the pre-change code, **and**
2. **green-after** — it passes on the post-change code, **and**
3. **deterministic ×3** — it runs the same result three times consecutively in the DTU, **and**
4. **asserts the property** the claim forbids violating — not the repro's incidental fixture values.

This is not advice — the `claim_ledger` **`graduate_test` op rejects (writes nothing)** unless
`asserts_property`, `red_before`, `green_after` are all true and `deterministic_runs >= 3`. Only a
graduated probe sets `adverse_state_test.exists = true` and thereby clears the safety limb; a
survived-but-ungraduated probe does **not**.

### Phase-2 ledger ops (on the same `claim_ledger` tool)

Phase 2 rides the **same** deterministic ledger as the static gate — the seam is the `run_id`, not
code coupling. Three Phase-2 ops extend the tool:

| Op | What it does | Honest-gate guarantee |
|---|---|---|
| `record_probe` | attaches a probe result to a claim | writes `claim.probe` only; **never** touches `adverse_state_test` — a *survived* probe does not by itself clear the safety limb |
| `defer_claim` | marks a probe-eligible claim `deferred` (rejects non-eligible claims) | never touches `adverse_state_test` — **deferred ≠ passed**; a deferred safety claim still blocks |
| `graduate_test` | records a graduated standing test | structurally rejects unless all four graduation criteria hold; on success sets `standing_test` **and** `adverse_state_test.exists = true` |

The full op surface is 12 ops: `add_claim`, `list_claims`, `record_verdict`, `record_lens_error`,
`record_debate`, `waive`, **`record_probe`**, **`defer_claim`**, **`graduate_test`**, `aggregate`,
`gate`, `render_matrix`. See `docs/tool-claim-ledger-contract.md`.

### Install / compose Phase 2

The dynamic bench pulls in a Digital-Twin dependency surface, so it is kept **off** the static
bundle and shipped as a separate standalone composition, `bundles/with-probing.yaml`:

```bash
# Phase-2 standalone: static gate + dynamic bench + DTU/parallax/amplifier-tester deps
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main#subdirectory=bundles/with-probing.yaml"
```

`with-probing.yaml` composes: the static behavior + the `claim-guard-probing` behavior (the 3 dynamic
agents + `claim_ledger`) + the execution primitives the pen-tester drives —
`parallax-discovery` (antagonist / execution-based falsification), `digital-twin-universe` (isolated
adverse-state construction), and `amplifier-tester` (DTU setup). It **requires a DTU-capable
environment** (Incus/Docker) because the `pen-tester` stands real adverse states up in a Digital Twin.

Run Phase 2 **after** a static `verify-claims` run, handing it the same `run_id`:

```text
execute claim-guard:recipes/probe-claims.yaml with:
  run_id:       "<the run_id produced by verify-claims>"   # the ledger seam
  repo_path:    "<path to the worktree under review>"
  gate_policy:  "blocking-with-waiver"
  probe_budget: 3        # max probes to actually run this changeset (DTU spend cap)
  max_rounds:   3
```

> **Honesty note — what is proven, and the one residual.** The full behavioural loop **has been run
> end-to-end in a twin, across both outcome branches** (`docs/EVALUATION.md` §8.2–§8.3):
>
> - **FALSIFIED → REFUTED.** `probe-claims` consumed an existing `verify-claims` ledger via the
>   `run_id` seam and drove `probe-designer` → `pen-tester` on the B-1 safety claim
>   (`clm_2a25c125`, *"a degraded server does not create a duplicate `Node`"*). The probe **made the
>   forbidden violation happen** — adverse 25/25 rounds duplicated, control 0/25 — and `REFUTED` was
>   recorded with `file:line` evidence. Correctly **not** graduated: a falsified probe is a new-defect
>   finding, not a survivor.
> - **SURVIVED → graduated.** The `max_delete` cap claim (`clm_c39773b8`, B-3) survived its probe and
>   `graduate_test` **ACCEPTED** it on all four criteria (red-before, green-after, deterministic ×3,
>   asserts-the-property), setting `standing_test` and `adverse_state_test.exists = true` — **gate limb
>   2 cleared**. The graduated test was independently re-run on the host: **21 passed.** It is a real,
>   committable pytest.
>
> **Fidelity is now confirmed against a real engine.** The B-1/B-3 runs above used the
> design-sanctioned lighter path (self-contained in-process models of the exact mechanisms). The B-1
> corruption claim was then **re-probed against a live Neo4j** (`docker neo4j:5`) using the **verbatim
> production `MERGE` query** — degraded (no `:Node` uniqueness constraint) produced duplicate `:Node`
> rows in **25/25 rounds (max 8, 165 extra rows)**, while the control (constraint present) never
> exceeded 1. This **reproduces** the in-process result, confirming the lighter models were faithful
> proxies (`docs/EVALUATION.md` §8.4). The live run drove the real production query directly rather
> than the full HTTP server — the same underlying mechanism. See `docs/KNOWN_ISSUES.md` (KI-2).

## Known issues

See [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md). Two headlines:

- **KI-1 — harvest reproducibility (closed at a revised bar, with an accepted residual).** The **gate
  verdict and the four-blocker catch are stable run-to-run**, and the **categories of concern** that
  surface are reproducible (measured concern-type overlap 0.93). But the **exact** claim matrix is
  **not** byte-reproducible — the harvesters vary in which claims they select and at what granularity,
  so claim counts differ between runs. **Trust the verdict and the blocker catch; treat the detailed
  matrix as indicative, not diffable.**
- **KI-2 — Phase-2 behavioural pen-testing (closed).** The behavioural loop is proven end-to-end
  across both outcome branches (FALSIFIED→REFUTED, SURVIVED→graduated), and the B-1 corruption claim
  was confirmed against a **live Neo4j** running the verbatim production `MERGE` query — the in-process
  models are faithful proxies (`docs/EVALUATION.md` §8.4). The live run drove the real query directly
  rather than the full HTTP server; same mechanism.

## License

MIT. See `LICENSE`.
