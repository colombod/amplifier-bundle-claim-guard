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

> **Status: MVP (static slice).** Ships the static claim-verification pipeline. The Phase-2
> dynamic half (behavioural penetration testing in an isolated environment) is *designed for* but
> not yet built — the ledger schema already carries the Phase-2 fields so it slots in without
> rework. See `docs/tool-claim-ledger-contract.md`.

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

**Verify it layered in** (any base bundle works — here `amplifier`):

```bash
amplifier run -B amplifier --mode single \
  "List any sub-agents named claim-guard:* you can delegate to, and whether the claim_ledger tool is available. Do not read code."
```

Real output from this exact command (app-composed onto a plain `-B amplifier` session):

```
Bundle 'amplifier' prepared successfully
...
 claim-guard:claim-harvester            Extracts the explicit claims a change makes
 claim-guard:purpose-inquisitor         Infers the implicit claims (what the change exists FOR)
 claim-guard:correspondence-auditor     Mandatory static refutation — prove a claim false against source
 claim-guard:test-correspondence-audi…  Demands a test that goes RED when the claimed property is violated
 claim-guard:chokepoint-mapper          Enumerates every path into a guarded mechanism (LSP incomingCalls)
 claim-guard:boundary-adversary         Finds the input value that inverts a cap/limit/threshold invariant

That's 6 agents — the harvest pair, the static core, and the conditional lenses.

claim_ledger tool: ✅ available.
```

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
| 4 discipline skills (harvesting, verify-against-source, …) | ❌ | ✅ |
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
├── bundle.md                              # thin standalone (includes foundation, modes, recipes, lsp, own behavior)
├── behaviors/claim-guard.yaml             # THE REUSABLE CAPABILITY: tool + 6 agents + awareness (this is what --app installs)
├── agents/                                # the 6 static-bench agents
│   ├── claim-harvester.md
│   ├── purpose-inquisitor.md
│   ├── correspondence-auditor.md
│   ├── test-correspondence-auditor.md
│   ├── chokepoint-mapper.md
│   └── boundary-adversary.md
├── context/claim-guard-awareness.md       # thin awareness pointer (~250 tokens)
├── modes/claim-guard.md                   # review posture — blocks write_file/edit_file (root-only)
├── skills/                                # concierge playbook + 4 discipline skills (root-only)
│   ├── claim-guard/                        # user-invocable: the concierge playbook
│   ├── claim-harvesting/
│   ├── verify-against-source/
│   ├── adverse-state-catalog/
│   └── properly-delivered-claim/
├── recipes/verify-claims.yaml             # the staged static pipeline (root-only)
├── modules/tool-claim-ledger/             # the deterministic ledger + gate (the trust anchor)
└── docs/
    ├── tool-claim-ledger-contract.md       # authoritative interface contract for the module
    └── EVALUATION.md                        # acceptance-evaluation methodology (reproducible)
```

The **`tool-claim-ledger`** Python module is the trust anchor: worst-wins aggregation, `file:line`
evidence enforcement, the gate rule, and stable claim IDs across runs. Its interface is specified
in `docs/tool-claim-ledger-contract.md`.

## Not built yet (Phase 2)

The dynamic bench — `probe-designer`, `pen-tester` (stands up a claim's adverse state in a Digital
Twin and actively attacks it), `regression-graduator` — and the `probe-claims.yaml` recipe. The
ledger schema already carries `probe_eligibility`, `adverse_state_test`, and the `DEFERRED` state
so Phase 2 composes on without reshaping anything.

## License

MIT. See `LICENSE`.
