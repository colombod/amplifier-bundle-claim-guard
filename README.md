# amplifier-bundle-claim-guard

An [Amplifier](https://github.com/microsoft/amplifier) bundle that runs an **adversarial
claim-verification gate** over a changeset before you merge it.

For every claim a change makes — commit messages, docstrings, spec and design docs, and the
*implicit* promises of its purpose — claim-guard locates the load-bearing code and tries to **prove
that claim FALSE against the actual shipped source**. It emits an auditable **claim-verification
matrix** and a deterministic **BLOCK / PASS / INDETERMINATE** verdict.

The operating question flips from *"does it work?"* to ***"how is this claim false?"*** The commit
message is a **hypothesis to disprove**, not a fact.

---

## What it does

It is the missing **implementation-layer** gate — the one that re-reads shipped code adversarially
against its own claims. Distinct from, and complementary to:

| Gate | Reasons about | Runs |
|---|---|---|
| Design council (`/council`) | intended mechanism, in prose | before code |
| Code review | "does this look correct" | after code, confirmatory |
| Happy-path E2E | success paths you thought of | after code, liveness |
| **claim-guard** | **claim ↔ shipped-code correspondence** | **after build, before merge** |

**The gate rule** (computed deterministically by the `claim_ledger` tool, never by an LLM) — merge
is **BLOCKed** if any of:

1. any claim aggregates to **REFUTED**;
2. any **safety** claim has **no adverse-state test that fails on violation**;
3. any claim aggregates to **UNTESTABLE** with no recorded human waiver;
4. any lens errored / returned no structured verdict → **INDETERMINATE** (never PASS);
5. **zero claims harvested** → **INDETERMINATE** (an empty claim list is a harvest failure, not a
   clean bill of health).

Aggregation across lenses for one claim is **worst-wins**:
`REFUTED > UNTESTABLE > CONFIRMED > N/A`.

### What ships

| Capability | What it is |
|---|---|
| **7 lens agents** (`claim-guard:*`) | the adversarial bench — two harvesters, two mandatory core auditors, three conditional lenses (see [The bench](#the-bench)) |
| **`claim_ledger` tool** (15 ops) | the trust anchor — deterministic worst-wins aggregation, `file:line` evidence enforcement, and the gate rule |
| **`/claim-guard` mode** | the review posture — blocks `write_file`/`edit_file` (the gate never edits the code it reviews); inert until activated |
| **`claim-guard-here` skill** | INLINE, model-invocable — the concierge playbook an agent loads to drive the gate **in the current session**. This is the agent path. |
| **`/claim-guard-review`** | the same gate in an **isolated forked** session, for a changeset the current session has not seen |
| **`verify-claims` recipe** | the optional staged Phase-1 pipeline, with Gate A / Gate B human approvals |
| **`probe-claims` recipe** | the Phase-2 dynamic behavioural pen-testing pass |
| **5 discipline skills** | claim harvesting, verify-against-source, adverse-state catalog, properly-delivered-claim, probe patterns |

### When to use it

Run claim-guard as a **pre-merge review gate over a changeset** — a diff or a PR (`base..head`),
with its commit messages and any linked design doc. **Not per-commit:** it reasons about the claims
a whole change makes, so a single commit mid-branch is usually the wrong unit.

It is **invoked deliberately**, not automatically. Wire it as a **manual pre-merge check** — the
point in your flow where you'd otherwise say *"this looks right, ship it."*

> **Status: two phases, both built and both exercised end-to-end.**
> **Phase 1 — the static gate (`verify-claims`)** is proven end-to-end against a real regression PR
> (see [*What a real run produces*](#what-a-real-run-produces)), and **re-validated at current
> `HEAD`** after the harvester rewrite (`docs/EVALUATION.md` §10 — still `BLOCK`, all four blockers
> caught).
> **Phase 2 — the dynamic behavioural pen-testing bench (`probe-claims`)** has been run end-to-end
> in a Digital Twin across **both** outcome branches: a **FALSIFIED** probe that empirically
> **REFUTED** a safety claim, and a **SURVIVED** probe **graduated into a standing regression test**
> that clears gate limb 2 (`docs/EVALUATION.md` §8.2–§8.3). **The fidelity of those runs is
> confirmed against a real engine:** the core B-1 corruption claim was re-probed against a **live
> Neo4j** using the verbatim production `MERGE` query — degraded (no `:Node` uniqueness constraint)
> produced duplicate `:Node` rows (25/25 rounds, max 8) while the control never exceeded 1,
> **reproducing** the in-process result (`docs/EVALUATION.md` §8.4).
> See [Two phases](#two-phases-static-gate--dynamic-pen-testing) and `docs/KNOWN_ISSUES.md` (KI-2).

---

## Quick Start

### 1. Install

There are two behaviors you can layer. Pick one — you do not need both.

**A) Static gate** (recommended) — the fast, always-available pre-merge gate; layers onto your
active bundle without pulling in foundation:

```bash
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main#subdirectory=behaviors/claim-guard.yaml" --app
```

**B) Full gate + Phase-2 pen-testing** — everything in A **plus** the dynamic behavioural
penetration-testing bench (probe-designer, pen-tester, regression-graduator) and the execution
primitives they drive (Digital Twin Universe, parallax-discovery, amplifier-tester). Layer this when
you want adverse-state probing on top of the static gate — it carries a heavier surface (DTU etc.),
which is exactly why it is a separate behavior:

```bash
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main#subdirectory=behaviors/claim-guard-probing.yaml" --app
```

**Standalone** — instead of layering, use a full root bundle as a dedicated session configuration
(includes foundation). `claim-guard` is static-only; `with-probing` is the Phase-2 variant:

```bash
# static gate as a primary bundle
amplifier bundle add git+https://github.com/colombod/amplifier-bundle-claim-guard@main
amplifier bundle use claim-guard

# full gate + Phase-2 as a primary bundle
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main#subdirectory=bundles/with-probing.yaml"
amplifier bundle use claim-guard-with-probing
```

**Which one?** `--app` composes the behavior onto **every** session, whatever primary bundle
(`-B …`) you run — you layer the capability instead of switching bundles. That is the normal
install: a pre-merge gate you carry with you. Start with **A (static)** — it settles most claims in
seconds and never pays the DTU surface; reach for **B (with probing)** when a safety/quantitative
claim needs first-hand adverse-state falsification. The **behavior is the product**; `bundle.md`
(and `bundles/with-probing.yaml`) are thin wrappers that exist only for the standalone path. Each
behavior is self-sufficient — it brings the `modes`, `recipes`, and `lsp` infra (and, for B, the
DTU/parallax/tester primitives) that its agents ride on — so layering it composes the whole gate.

> **A registered mode is inert until activated.** Layering claim-guard cannot block your host
> bundle's `write_file` — `/claim-guard` is *available*, never auto-active.

> You may see `⚠ Could not resolve provider module … — skipping plaintext-secret scan` warnings
> during `bundle add`; they're harmless (the scan is skipped) and the add still succeeds.

### 2. Verify it layered in

Any base bundle you actually have works — here `foundation`, which ships by default; substitute
whichever primary bundle you run:

```bash
amplifier run -B foundation --mode single \
  "List sub-agents named claim-guard:*, whether the claim_ledger tool is available and its op count, any /claim-guard slash commands, and whether the mode, recipes, and LSP tools are present. Do not read code."
```

Observed from the behavior-`--app` install, composed onto a plain `-B foundation` session
(captured 2026-08-21):

```
(1) 7 claim-guard:* agents — boundary-adversary, chokepoint-mapper, claim-harvester,
    correspondence-auditor, empirical-verifier, purpose-inquisitor, test-correspondence-auditor
(2) claim_ledger tool: available — 15 operations (add_claim, add_claims, aggregate, defer_claim,
    gate, graduate_test, list_claims, record_debate, record_lens_error, record_probe,
    record_verdict, render_matrix, report, start_run, waive)
(3) /claim-guard (the mode) + /claim-guard-review (isolated forked run) registered;
    claim-guard-here is model-invoked via load_skill, not a slash command
(4) mode claim-guard available, NOT activated (inert — your host's write_file is unaffected)
(5) mode tool: yes · recipes tool: yes · LSP tool: yes
```

### 3. Give the gate its inputs

A run needs three things about the revision under review:

1. **the shipped source tree** at that revision (a worktree/checkout — the code actually reviewed);
2. **the diff** for the changeset (`base..head`);
3. **the commit messages** for that range (a primary claim source).

```bash
# Generic placeholders — substitute your repo/range:
git -C /path/to/repo worktree add /tmp/review-worktree <HEAD_SHA>
git -C /path/to/repo diff <BASE_SHA>..<HEAD_SHA> > /tmp/change.diff
git -C /path/to/repo log  <BASE_SHA>..<HEAD_SHA> > /tmp/commits.txt
```

Then the concierge **harvests** explicit + implicit claims, **fans the lens bench out cold**,
**debates** to consensus (one verbatim-relay round when lenses conflict), **aggregates** via
`claim_ledger`, and emits the **matrix** + a **BLOCK / PASS / INDETERMINATE** verdict — every
CONFIRMED/REFUTED carrying a `file:line` anchor, every REFUTED a counter-case.

---

## Worked workflows

Both audiences drive the same bench. The invariant either way: **load the `claim-guard-here`
playbook and let it drive.** Driving `claim_ledger` op-by-op without the playbook produces an
unattributed, ungated result.

### Agent path — just ask, in any session

With the behavior layered (`--app`), the gate is available in every session. You do not name a
skill or a tool; you state the job. The agent loads the `claim-guard-here` playbook itself, harvests
the claims, fans the lenses out cold, aggregates via `claim_ledger`, and returns the matrix and the
verdict.

> *"Review this changeset before I merge — is it safe to ship? Gate `git diff main...HEAD`. Here
> are the commit messages and the linked design doc. Harvest explicit + implicit claims, fan the
> lenses out cold, and give me the matrix plus the BLOCK/PASS verdict with `file:line` evidence.
> Do not edit any code."*

The fuller form, when you've prepared the three inputs from Quick Start step 3:

> *"Run the claim-guard gate. Source under review: `/tmp/review-worktree`. Diff: `/tmp/change.diff`.
> Commit messages: `/tmp/commits.txt`. Harvest explicit + implicit claims (UNION), fan the lenses
> out cold, run one debate round on any conflict, then call `claim_ledger` to aggregate and gate.
> Give me the matrix and the verdict with `file:line` evidence. Do not edit any code."*

### Human path — the slash commands

```text
# The normal human entry point — activates the review posture (write_file/edit_file blocked)
# and starts the concierge playbook on that changeset:
/claim-guard <BASE_SHA>..<HEAD_SHA>

# …or the same gate in an isolated forked session, for a changeset this session has not seen:
/claim-guard-review <BASE_SHA>..<HEAD_SHA>
```

### Staged path — the `verify-claims` recipe

Use this when you want the run to **pause for human approval**: Gate A to review the harvested
claims before verification, Gate B at the MVP boundary before dynamic probing.

```text
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

A run produces two things: a **claim-verification matrix** (one row per claim) and a **gate
verdict**. Both are computed by the `claim_ledger` tool — deterministic arithmetic over the ledger,
never an LLM judgement. The full interface is in
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
- **limb 5** — **zero claims harvested** → `INDETERMINATE` (reason `zero-claims-harvested`) — an
  empty claim list is a harvest failure, not a clean bill of health

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

## The bench

**Harvesters** (cold, independent, UNIONed — inference can only *add* claims, never remove one)
- **`claim-harvester`** — *"What does this change explicitly say it does?"*
- **`purpose-inquisitor`** — *"What does this change exist FOR, and what does that silently promise?"*

**Mandatory core** (runs on every claim)
- **`correspondence-auditor`** — *"Does the load-bearing code actually do what the claim says — and where is the line that proves it?"*
- **`test-correspondence-auditor`** — *"Is there a test that goes RED when this property is violated, in the adverse state?"*

**Conditional lenses** (triggered by claim type / changeset shape; exclusion recorded with a reason)
- **`chokepoint-mapper`** — *"Which paths into this mechanism are NOT guarded?"* (the "one branch over" catcher; uses LSP `incomingCalls`)
- **`boundary-adversary`** — *"What input value inverts this invariant?"*
- **`empirical-verifier`** — *"Stop reading — what happens when I actually RUN it?"* The council's
  **empirical member**: every other lens reads the source, this one **executes** — the shipped test
  that targets the property, else a minimal in-process repro, else the real function/tool directly,
  else (only if one is available and warranted) a disposable container or a DTU. It runs only in a
  safe, isolated, disposable environment it fully controls — never against anything real. Its
  verdict carries **empirical evidence** — the exact command and the observed output — alongside the
  `file:line` of what was exercised. Rostered when the changeset has a runnable/testable artifact.
  It is a *lighter first-hand check* than the Phase-2 `pen-tester`, which builds full adverse states.

The orchestration is **council-shaped**: a concierge fans the bench out cold, runs a
**debate-to-consensus** loop (verbatim relay, no curation), and synthesizes a verdict **with
recorded dissent** plus a roster manifest — mirroring `amplifier-bundle-council`. An optional input
feeds a prior **design-council verdict** in as claims (every addressed `FAIL`/`CONCERN` becomes a
claim to verify against the shipped code).

---

## Two phases: static gate + dynamic pen-testing

claim-guard runs as **two phases joined only by a shared ledger** — not by code coupling. Phase 2
reads the ledger Phase 1 wrote (by `run_id`) and composes onto **any** completed static run.

| | **Phase 1 — `verify-claims`** (static gate) | **Phase 2 — `probe-claims`** (dynamic pen-testing) |
|---|---|---|
| Question | *"Does the shipped code do what the claim says?"* | *"Can I make the forbidden thing actually happen?"* |
| Method | read the source adversarially; refute against `file:line` | stand the adverse state up in a **Digital Twin** and attack it |
| Bench | 7 static lenses (harvest pair + 2 core + 3 conditional, incl. `empirical-verifier`) | 3 dynamic agents (`probe-designer`, `pen-tester`, `regression-graduator`) |
| Verdicts | `CONFIRMED / REFUTED / UNTESTABLE` (+ deterministic gate) | empirical `REFUTED` (new defect) or a **graduated standing test** |
| Needs | any session (LSP for the chokepoint lens) | a **DTU-capable environment** (Incus/Docker) |
| Terminates | at Gate B ("proceed to dynamic probing?") | at the final re-gate over the enriched ledger |
| Status | **proven end-to-end** on a real PR, **re-validated at `HEAD`** (§10) | **run end-to-end in a twin across both outcome branches** (FALSIFIED→REFUTED, SURVIVED→graduated), **and confirmed against a live Neo4j** (§8.4) |

**The ledger is the seam.** `verify-claims` produces `.claim-guard/<run_id>/ledger.json`;
`probe-claims` takes that same `run_id`, probes the claims whose *type* requires behavioural proof,
and writes the empirical results back to the same ledger. There is no other connection between the
two recipes — deleting Phase 2 leaves Phase 1 completely intact, and Phase 2 can be run days later on
a static run that already finished.

---

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

The full op surface is **15 ops**: `add_claim`, `list_claims`, `record_verdict`,
`record_lens_error`, `record_debate`, `waive`, **`record_probe`**, **`defer_claim`**,
**`graduate_test`**, `aggregate`, `gate`, `render_matrix`, plus the three **concierge ops** below.
See `docs/tool-claim-ledger-contract.md`.

### Concierge ops — mechanical, not hand-driven

Three ops exist so the concierge never has to invent a `run_id`, never has to fire one
`add_claim` per claim, and never has to stitch the verdict together itself:

| Op | What it does | Why it exists |
|---|---|---|
| `start_run` | creates a run and returns its `run_id` (`{ gate_policy? }` → `{ run_id }`) | the run_id comes **from the ledger**; the agent never fabricates or guesses one |
| `add_claims` | bulk-adds a whole harvested batch in one call | one call for N claims instead of N hand-driven `add_claim`s; a malformed element is reported in `errors` and never aborts the batch |
| `report` | `gate` + `render_matrix` in a single round trip | the verdict and the matrix it explains are always computed together, from the same ledger state |

**The ledger's on-disk shape is private.** Read it through `claim_ledger list_claims` /
`claim_ledger report` — never by opening `.claim-guard/` with `read_file`, `cat`, or `jq`. Every
interaction goes through the tool; that is what makes a run's context un-fudgeable.

### Install / compose Phase 2

The dynamic bench pulls in a Digital-Twin dependency surface, so it lives in a **separate behavior**
(`behaviors/claim-guard-probing.yaml`) kept **off** the static behavior — layering the static
`claim-guard.yaml` never pays the DTU surface. To get Phase 2, layer the probing behavior instead
(the same `--app` pattern as the static gate — see [Quick Start → Install, option B](#1-install)):

```bash
# Layer the FULL gate + Phase-2 onto every session:
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main#subdirectory=behaviors/claim-guard-probing.yaml" --app

# Or as a dedicated standalone session:
amplifier bundle add "git+https://github.com/colombod/amplifier-bundle-claim-guard@main#subdirectory=bundles/with-probing.yaml"
amplifier bundle use claim-guard-with-probing
```

The `claim-guard-probing` behavior is self-sufficient: it composes the static behavior (the static
bench + `claim_ledger` + `modes`/`recipes`/`lsp` + the `/claim-guard` mode + awareness), the 3
dynamic agents (probe-designer, pen-tester, regression-graduator), and the execution primitives the
pen-tester drives — `parallax-discovery` (antagonist / execution-based falsification),
`digital-twin-universe` (isolated adverse-state construction), and `amplifier-tester` (DTU setup) —
all as **behaviors**, never root bundles. It **requires a DTU-capable environment** (Incus/Docker)
because the `pen-tester` stands real adverse states up in a Digital Twin.

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

---

## Repository structure

```
amplifier-bundle-claim-guard/
├── bundle.md                              # thin STATIC standalone wrapper (foundation + own behavior)
├── bundles/with-probing.yaml              # PHASE-2 standalone: static + dynamic behaviors + DTU/parallax/tester
├── behaviors/
│   ├── claim-guard.yaml                   # STATIC capability, SELF-SUFFICIENT: tool + tool-skills + hooks-mode
│   │                                      #   + modes/recipes/lsp + 7 agents + awareness
│   │                                      #   (--app option A: the static gate)
│   └── claim-guard-probing.yaml           # PHASE-2 capability, SELF-SUFFICIENT: includes claim-guard.yaml
│                                          #   + 3 dynamic agents + DTU/parallax/tester behaviors
│                                          #   (--app option B: full gate + Phase-2)
├── agents/                                # 7 static-bench + 3 dynamic-bench agents
│   ├── claim-harvester.md                 # static — harvester
│   ├── purpose-inquisitor.md              # static — harvester
│   ├── correspondence-auditor.md          # static — mandatory core
│   ├── test-correspondence-auditor.md     # static — mandatory core
│   ├── chokepoint-mapper.md               # static — conditional
│   ├── boundary-adversary.md              # static — conditional
│   ├── empirical-verifier.md              # static — conditional; verifies by EXECUTION, not reading
│   ├── probe-designer.md                  # Phase 2
│   ├── pen-tester.md                      # Phase 2
│   └── regression-graduator.md            # Phase 2
├── context/claim-guard-awareness.md       # thin awareness pointer (~250 tokens)
├── modes/claim-guard.md                   # review posture — blocks write_file/edit_file; shortcut /claim-guard
│                                          #   (registered by the behavior via hooks-mode)
├── skills/                                # 2 concierge entry points + 5 discipline skills
│   │                                      #   (registered by the behavior via tool-skills)
│   ├── claim-guard-here/                  # INLINE, model-invocable: the agent-path concierge playbook
│   ├── claim-guard-review/                # fork, human-only: /claim-guard-review — isolated run
│   ├── claim-harvesting/
│   ├── verify-against-source/
│   ├── adverse-state-catalog/
│   ├── properly-delivered-claim/
│   └── probe-patterns/                    # Phase 2: per-claim-type probe design discipline
├── recipes/
│   ├── verify-claims.yaml                 # Phase 1: the staged static pipeline
│   └── probe-claims.yaml                  # Phase 2: dynamic pen-testing pipeline, consumes the ledger by run_id
├── modules/tool-claim-ledger/             # the deterministic ledger + gate (the trust anchor; 15 ops)
└── docs/
    ├── tool-claim-ledger-contract.md      # authoritative interface contract for the module
    ├── EVALUATION.md                      # acceptance methodology, Phase-2 (DTU) runs, at-HEAD re-validation
    └── KNOWN_ISSUES.md                    # KI-1 harvest reproducibility (closed at revised bar), KI-2 Phase-2 (closed)
```

The **`tool-claim-ledger`** Python module is the trust anchor: worst-wins aggregation, `file:line`
evidence enforcement, the gate rule, and stable claim IDs across runs. Its interface is specified
in `docs/tool-claim-ledger-contract.md`.

---

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

## Related

- [Amplifier](https://github.com/microsoft/amplifier) — the runtime this bundle composes onto
- [`amplifier-bundle-council`](https://github.com/microsoft/amplifier-bundle-council) — the
  design-time council whose orchestration shape claim-guard mirrors (and whose verdict can be fed in
  as claims)
- [`amplifier-bundle-digital-twin-universe`](https://github.com/microsoft/amplifier-bundle-digital-twin-universe)
  — the isolated environments the Phase-2 `pen-tester` stands adverse states up in

## License

MIT. See `LICENSE`.
