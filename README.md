# amplifier-bundle-claim-guard

**An adversarial claim-verification gate for Amplifier.** For every claim a changeset makes,
claim-guard locates the load-bearing code and tries to **prove the claim FALSE against the actual
shipped source**; it emits an auditable **claim-verification matrix**; and it **gates merge** on
any REFUTED claim or any safety claim with no adverse-state test.

It is the missing **implementation-layer** gate — the one that reads shipped code adversarially
against its own claims. It is distinct from, and complementary to:

| Gate | Reasons about | Runs |
|---|---|---|
| Design council (`/council`) | intended mechanism, in prose | before code |
| Code review | "does this look correct" | after code, confirmatory |
| Happy-path E2E | success paths you thought of | after code, liveness |
| **claim-guard** | **claim ↔ shipped-code correspondence** | **after build, before merge** |

The operating question flips from *"does it work?"* to ***"how is this claim false?"*** The commit
message is a **hypothesis to disprove**, not a fact.

> **Status: MVP (static slice).** Ships the static claim-verification pipeline. The Phase-2
> dynamic half (behavioural penetration testing in an isolated environment) is *designed for* but
> not yet built — the ledger schema already carries the Phase-2 fields so it slots in without
> rework. See `docs/tool-claim-ledger-contract.md`.

---

## What it does (the one job)

1. **Harvest** every claim the change makes — from commit messages, the PR body, linked
   design/spec docs, and (highest yield) **docstrings and inline comments**. A second, independent
   harvester infers the **implicit** claims: what the change *exists for*, even when unstated.
   The two are **UNIONed, never intersected** — inference can only add claims, never remove one.
   An optional input feeds a prior **design-council verdict** in as claims (every addressed
   `FAIL`/`CONCERN` becomes a claim to verify against the shipped code).
2. **Verify statically** — a bench of orthogonal adversarial lenses fans out **cold and
   independent** over the claims and tries to refute each against the source, returning
   `CONFIRMED | REFUTED | UNTESTABLE` with a `file:line` anchor and a counter-case.
3. **Aggregate + gate** — the `claim_ledger` tool computes the verdict matrix and the gate
   **deterministically** (never an LLM).

The orchestration is **council-shaped**: a concierge fans the bench out cold, runs a
**debate-to-consensus** loop (verbatim relay, no curation), and synthesizes a verdict **with
recorded dissent** plus a roster manifest — mirroring `amplifier-bundle-council`.

## The bench (MVP)

**Harvesters**
- **`claim-harvester`** — *"What does this change explicitly say it does?"*
- **`purpose-inquisitor`** — *"What does this change exist FOR, and what does that silently promise?"*

**Mandatory core** (runs on every claim)
- **`correspondence-auditor`** — *"Does the load-bearing code actually do what the claim says — and where is the line that proves it?"*
- **`test-correspondence-auditor`** — *"Is there a test that goes RED when this property is violated, running in the adverse state?"*

**Conditional lenses** (triggered by claim type, exclusion recorded with a reason)
- **`chokepoint-mapper`** — *"Which paths into this mechanism are NOT guarded?"* (the "one branch over" catcher; uses LSP `incomingCalls`)
- **`boundary-adversary`** — *"What input value inverts this invariant?"*

## The gate rule

Merge is **BLOCKed** if any of:
1. any claim aggregates to **REFUTED**;
2. any **safety** claim has **no adverse-state test that fails on violation**;
3. any claim aggregates to **UNTESTABLE** with no recorded human waiver;
4. any lens errored / returned no structured verdict → **INDETERMINATE** (never PASS);
5. **zero claims harvested** → **INDETERMINATE** (never PASS — an empty claim list is a harvest
   failure, not a clean bill of health).

Aggregation across lenses for one claim is **worst-wins**:
`REFUTED > UNTESTABLE > CONFIRMED > N/A`. An abstention never lowers an aggregate; a missing
result never counts as CONFIRMED.

## How to run

### Interactive (concierge)

Invoke the `/claim-guard` skill with the changeset:

```
/claim-guard git diff main...HEAD    (with the commit messages + linked design docs to hand)
```

It resolves the roster, runs the cold fan-out, drives the debate loop, and synthesizes the matrix
with recorded dissent. Activate the `/claim-guard` mode first to structurally block edits to the
code under review.

### Pipeline (recipe)

```
execute claim-guard:recipes/verify-claims.yaml with:
  changeset: "<diff / PR ref / branch range>"
  commit_messages: "<git log text>"
  design_docs: "<paths or inline text of linked design/spec docs>"
  council_verdict: "<optional: a prior /council verdict to fold in as claims>"
  repo_path: "<path to the repo under review>"
  gate_policy: "blocking-with-waiver"   # advisory | blocking-with-waiver | blocking
  max_rounds: 3
```

The recipe guarantees the neutral changeset digest, the cold/independent harvest, the roster
manifest, and the deterministic gate. It pauses at **Gate A** (review the harvested claim ledger
before spending verification effort) and terminates at **Gate B** (the MVP boundary — proceed to
dynamic probing is Phase 2). Debate and synthesis are concierge-driven per the `/claim-guard`
playbook.

## Composition

```
amplifier-bundle-claim-guard/
├── bundle.md                              # thin standalone (includes foundation, modes, recipes, lsp, own behavior)
├── behaviors/claim-guard.yaml             # the reusable capability: tool + agents + context
├── agents/                                # the 6 static-bench agents
│   ├── claim-harvester.md
│   ├── purpose-inquisitor.md
│   ├── correspondence-auditor.md
│   ├── test-correspondence-auditor.md
│   ├── chokepoint-mapper.md
│   └── boundary-adversary.md
├── context/claim-guard-awareness.md       # thin awareness pointer (~250 tokens)
├── modes/claim-guard.md                   # review posture — blocks write_file/edit_file
├── skills/                                # concierge playbook + 4 discipline skills
│   ├── claim-guard/                        # user-invocable: the concierge playbook
│   ├── claim-harvesting/
│   ├── verify-against-source/
│   ├── adverse-state-catalog/
│   └── properly-delivered-claim/
├── recipes/verify-claims.yaml             # the staged static pipeline
├── modules/tool-claim-ledger/             # the deterministic ledger + gate (implemented separately)
└── docs/tool-claim-ledger-contract.md     # authoritative interface contract for the module
```

The **`tool-claim-ledger`** Python module is the trust anchor (worst-wins aggregation, `file:line`
evidence enforcement, the gate rule, stable claim IDs across runs). Its interface is specified in
`docs/tool-claim-ledger-contract.md`; the implementation is a separate step.

## Not built yet (Phase 2)

The dynamic bench — `probe-designer`, `pen-tester` (stands up a claim's adverse state in a Digital
Twin and actively attacks it), `regression-graduator` — and the `probe-claims.yaml` recipe. The
ledger schema already carries `probe_eligibility`, `adverse_state_test`, and the `DEFERRED` state
so Phase 2 composes on without reshaping anything.

## License

MIT. See `LICENSE`.
