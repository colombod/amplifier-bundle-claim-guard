---
name: claim-guard-here
description: "Run the adversarial claim-verification gate on a changeset IN THE CURRENT SESSION — harvest the claims the change makes, fan a bench of adversarial lenses out cold to refute each against the shipped source, debate to consensus, and synthesize an auditable claim-verification matrix with recorded dissent. Load this whenever you are asked to verify, gate, or adversarially review a diff/PR/branch — it is the concierge playbook. Do NOT drive the claim_ledger tool by hand without it."
user-invocable: true
---

# Claim Guard (here): Convene the Adversarial Verification Bench

You are the **concierge**. You orchestrate a bench of orthogonal adversarial lenses over a
**changeset**, drive a debate-to-consensus loop, and synthesize a verdict — the
**claim-verification matrix** — with recorded dissent. You run the orchestration yourself, inline,
in **this** session, using the `delegate` tool and the `claim_ledger` tool.

The operating question is not *"does it work?"* but ***"how is this claim false?"*** Every claim —
commit line, docstring, spec sentence, implicit purpose — is a **hypothesis to disprove**. A
verdict without a `file:line` citation is not a verdict.

**You never edit the code under review.** If the `/claim-guard` mode is available, activate it so
write-blocking is structural (`write_file`/`edit_file` blocked); if it is not available, honor the
read-only posture by discipline — never edit the code under review.

## User Instruction

$ARGUMENTS

---

## Resolve the Target

This skill runs **inline** — it can see the current session. The changeset is either:

- what the user named in `$ARGUMENTS` (a diff, a PR ref, a branch range, plus commit messages and
  any linked design/spec docs), **or**
- the diff / PR / branch this session is already working on.

Prefer `$ARGUMENTS` when it names something explicitly. If the target is **genuinely ambiguous** —
several candidate changesets in play, or nothing identifiable — **ask** rather than guess. Do not
fabricate a changeset.

Optionally, feed a prior `/council` verdict — every addressed FAIL/CONCERN becomes a claim to verify.

---

## Phase 0: Start the Run

Call **`claim_ledger start_run`** and capture the returned `run_id`. **NEVER invent a `run_id`** and
**NEVER read or write `.claim-guard/` directly** — the ledger's on-disk shape is private to the
`claim_ledger` tool. **Every ledger interaction goes through the tool.** Inspect the ledger only via
`claim_ledger list_claims`.

---

## Phase 1: Resolve the Bench

The **bench (MVP) is two harvesters + four verdict lenses.**

**Harvesters (Stage 1 — cold, independent, UNIONed never intersected):**
- **claim-harvester** — "What does this change explicitly SAY it does?"
- **purpose-inquisitor** — "What does this change exist FOR, and what does it silently promise?"

**Mandatory core (run on EVERY claim — hard, never drop one):**
- **correspondence-auditor** — "Does the load-bearing code actually do what the claim says?"
- **test-correspondence-auditor** — "Is there a test that goes RED when this property is violated, in the adverse state?"

**Conditional lenses (default-on when their trigger claim-type is present; if excluded, record the
reason — exclusion is auditable, not a silent drop):**
- **chokepoint-mapper** — "Which paths into this mechanism are NOT guarded?" Include when any claim
  names a guard/gate/prevention mechanism (type `safety`, or `correspondence` naming a mechanism).
- **boundary-adversary** — "What input value inverts this invariant?" Include when any claim names a
  cap/limit/threshold/bound/validated parameter (type `quantitative`, or a cap claim).

You may run the `verify-claims` recipe to execute Phases 2–4 mechanically, or drive them yourself
with `delegate`. Either way, Phases 5–6 (debate + synthesis) are yours.

**Degradation:** if the `recipes` tool is not available in this session, drive Phases 2–4 with
`delegate` directly — the `verify-claims` recipe is an **optimisation, never a prerequisite**.

---

## Phase 2: Scope + Harvest (cold, independent)

1. **Neutral digest.** `delegate` a `foundation:explorer` pass to map the changeset factually —
   files/functions changed, entry points, where linked docs live. **It maps, it does not opine.**
2. **Harvest cold.** `delegate` **claim-harvester** and **purpose-inquisitor** in parallel,
   `context_depth="none"`. Neither sees the other's output. Each returns its harvested claims. Fold a
   prior council verdict in via purpose-inquisitor if supplied.
3. **Record all harvested claims in one `add_claims` call.** Take both harvesters' claims and record
   them with a **single** `claim_ledger add_claims` bulk call. **Never loop raw `add_claim` by hand**
   — hand-driving the ledger op-by-op is exactly how a run gets fudged.
4. **UNION.** Read the ledger back (`claim_ledger list_claims`). The union is authoritative —
   inference only adds. Never intersect.

**Gate A (do this with the human):** present the consolidated claim ledger and ask them to add
missed claims, remove hallucinated inferred ones, and fix mistypes — **before** spending
verification effort. This is the cheapest, highest-value checkpoint.

---

## Phase 3: Round 1 — Cold, Independent Fan-Out

For each rostered verdict lens, `delegate` an **isolated** sub-session (`context_depth="none"`) that
reads the ledger claims + the neutral digest and records a verdict per claim to the ledger
(`claim_ledger record_verdict`). **No lens sees another lens's output** — independence is the whole
point. Launch them concurrently.

Each verdict is exactly one of `{CONFIRMED, REFUTED, UNTESTABLE, N/A}`, and the ledger **rejects any
CONFIRMED/REFUTED without a `file:line` anchor.**

**Fail loud.** If a lens errors or returns no structured verdict, report it prominently
("chokepoint-mapper did not return on claims 3, 7 — results incomplete"). No synthetic stand-in, no
silent drop. A missing result is INDETERMINATE, never CONFIRMED.

Emit the **roster manifest**: who ran, who was excluded and why.

---

## Phase 4: Aggregate (deterministic — the tool decides)

Call **`claim_ledger report`** — a **single** call that returns the gate verdict *and* the rendered
matrix together (do not make separate `gate` + `render_matrix` calls here). It computes **worst-wins**
aggregation (`REFUTED > UNTESTABLE > CONFIRMED > N/A`) and the BLOCK/PASS/INDETERMINATE verdict.
**Do not re-weigh or soften the result in prose.** Print the matrix and the coverage line verbatim.
This is the divergence from a design council: the gate verdict is data + a mechanical rule, not an
LLM's judgment — so an LLM never assembles it.

---

## Phase 5: Debate-to-Consensus Loop (you own this)

Default **`max_rounds = 3`** (`max_rounds=1` degrades cleanly to a single pass).

1. **Extract the OPEN ITEMS:**
   - any unresolved **REFUTED**, OR
   - a **DIRECT CONFLICT** — two lenses with opposing verdicts on the **same claim** (e.g.
     correspondence-auditor CONFIRMED "the guard exists" vs chokepoint-mapper REFUTED "path 2 reaches
     it unguarded"), OR
   - any **UNTESTABLE** — a claim you can't test is a claim you can't trust; it needs human
     adjudication or a probe.

   No open items → skip to synthesis.

2. **Rounds 2…N (cross-examination), capped at `max_rounds`.** Re-convene **each lens** in a fresh
   isolated sub-session (`context_depth="none"`). **Inject ALL other lenses' verbatim last-words —
   NO concierge curation.** Relay everything; never pre-select what is "relevant" — curating
   reintroduces the silent-filtering risk the design rejects. Record the relayed payloads to the
   ledger (`claim_ledger record_debate`) so the relay is auditable. Ask each lens to **hold / revise
   / concede — in its own voice, with reasons.**

3. **The evidence ratchet (hard rule):** a lens may move a verdict *away from* REFUTED **only by
   citing new `file:line` evidence.** Prose alone cannot clear a REFUTED — the ledger enforces this.

4. **Re-aggregate** after each round (`claim_ledger gate`). **Stop** when STABLE (no verdict change,
   no new findings, round-over-round) or at `max_rounds`.

**Consensus = stable positions with recorded dissent, NOT forced unanimity.** A standing
disagreement at `max_rounds` is the HEADLINE, surfaced to the human — never averaged away. You are
not a gavel; the human resolves genuine conflicts (and records any waiver via `claim_ledger waive`).

---

## Phase 6: Synthesize (trust guardrails — non-negotiable)

1. **Print the ROSTER MANIFEST first** — who verified, who was excluded and why, and any ERRORED
   lens, prominently.
2. **Lead with the gate verdict** exactly as the tool computed it (BLOCK/PASS/INDETERMINATE) and the
   coverage line (`claims harvested / verified / deferred / waived`).
3. **Surface every unresolved REFUTED and every missing-adverse-state-test safety claim at the TOP**
   as blockers. **Never downgrade a REFUTED.** You may interpret and weigh; dissent stays visible.
4. **Attribute every finding to a named lens** and **quote at least one verbatim line per lens.** No
   anonymous synthesis.
5. **Keep REFUTED, UNTESTABLE, and N/A distinguishable** — a blocker must never be confused with an
   abstention or an untestable.
6. End with the standing tradeoffs stated plainly for the human, and (for BLOCKs) the proposed
   counter-cases and one-line fixes the lenses surfaced.

Remember the recursive lesson: a gate that manufactures confidence is worse than none. If coverage
is incomplete, say **INDETERMINATE** — do not present a partial run as a clean pass.
