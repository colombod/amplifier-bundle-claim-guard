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

**The `run_id` is the binding value you must propagate — treat it like a session key.** Two ledger
write-paths depend on it, and they fail *differently*:

- **Verdict lenses (Phase 3) and re-convened lenses (Phase 5)** run in **isolated** sub-sessions
  (`context_depth="none"`) and call `claim_ledger record_verdict` **themselves**. A lens not handed
  this exact `run_id` passes `null`/empty; `record_verdict` **rejects it loudly**, so the verdict is
  *lost* and the claim silently stays `PENDING`.
- **The Phase-2 harvest write (`add_claims`) is worse:** `add_claim`/`add_claims` do **NOT** reject a
  blank/omitted `run_id` — they **silently FORK a new run** and strand the whole harvest off your
  intended run (a known tool seam; the refuse-empty guard is **not yet built**). A delegated
  harvester that records for itself without the `run_id` therefore vanishes with **no error at all**.

Therefore, from here on: **every `delegate` that will touch the ledger — lens OR harvester — must be
handed this exact `run_id`, verbatim; and the concierge, never a sub-agent, owns every `add_claims`
write (Phase 2), with the literal `run_id` in the call.** Never let any sub-agent infer, default, or
invent it, and never issue an `add_claims`/`add_claim` with a blank `run_id`.

---

## Phase 1: Resolve the Bench

The **bench (MVP) is two harvesters + five verdict lenses.**

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
- **empirical-verifier** — "Can I reproduce this claim by executing it?" Include when the changeset
  has a runnable/testable artifact (executable code, or runnable tests). This is the bench's only
  lens that **runs** rather than reads — it produces first-hand evidence (a real command and its real
  output). Record include/exclude with a reason, as with every conditional lens.

You may run the `verify-claims` recipe to execute Phases 2–4 mechanically, or drive them yourself
with `delegate`. Either way, Phases 5–6 (debate + synthesis) are yours.

**Degradation:** if the `recipes` tool is not available in this session, drive Phases 2–4 with
`delegate` directly — the `verify-claims` recipe is an **optimisation, never a prerequisite**.

---

## Phase 2: Scope + Harvest (cold, independent)

1. **Neutral digest.** `delegate` a `foundation:explorer` pass to map the changeset factually —
   files/functions changed, entry points, where linked docs live. **It maps, it does not opine.**
2. **Harvest cold.** `delegate` **claim-harvester** and **purpose-inquisitor** in parallel,
   `context_depth="none"`. Neither sees the other's output. **Instruct each harvester to RETURN its
   claims to you and NOT record them itself** — a harvester that self-records without the `run_id`
   silently forks a stranded run (Phase 0), losing the entire harvest with no error. (If a harvester
   can only record, hand it the literal `run_id`.) Fold a prior council verdict in via
   purpose-inquisitor if supplied.
3. **Record all harvested claims in one `add_claims` call.** Take both harvesters' returned claims and
   record them yourself with a **single** `claim_ledger add_claims` bulk call, **passing the literal
   `run_id` in that call — never blank** (a blank `run_id` here silently forks a new run rather than
   erroring). **Never loop raw `add_claim` by hand** — hand-driving the ledger op-by-op is exactly how
   a run gets fudged.
4. **UNION.** Read the ledger back (`claim_ledger list_claims`). The union is authoritative —
   inference only adds. Never intersect.

**Gate A (do this with the human):** present the consolidated claim ledger and ask them to add
missed claims, remove hallucinated inferred ones, and fix mistypes — **before** spending
verification effort. This is the cheapest, highest-value checkpoint.

---

## Phase 3: Round 1 — Cold, Independent Fan-Out

### Step 0 — Declare the roster BEFORE you fan out (or the run is INDETERMINATE)

The bench you resolved in Phase 1 is a *decision*; `claim_ledger declare_roster` is what makes it
**data the gate can check you against.** Call it with the literal `run_id`, **before** the verdict
fan-out:

- **`mandatory`:** `correspondence-auditor` + `test-correspondence-auditor` — they run on every claim.
- **`conditional`** (keyed by lens, each with `types`, `included`, `reason` — the same include/exclude
  call you already made in Phase 1, now recorded): `chokepoint-mapper` on `types: ["safety"]`,
  `boundary-adversary` on `types: ["quantitative"]`. An excluded lens is declared with
  `included: false` **and its reason** — that is what makes the exclusion auditable rather than a
  silent drop.
- **Do NOT roster `empirical-verifier`** (nor any dynamic-probing lens such as `pen-tester`). It runs
  opportunistically, only when the changeset has something executable; rostering it would mint a
  **permanent, unclosable** `lens-coverage-gap` on every claim it happened not to reach.

The roster is a **policy**, and `expected_lenses` is derived per claim from `(claim.type, roster)` on
every read — so a Gate-A retype automatically re-routes that claim's expected lenses; you do not
re-declare for a retype. Re-declaring mid-run *is* supported (the prior roster is pushed to
`roster_history`, never silently overwritten) if the bench genuinely changes.

**An undeclared roster makes the whole run INDETERMINATE.** Gate limb 4c reads roster coverage and
emits `no-roster-declared` when claims were harvested but no roster was declared, plus
`lens-coverage-gap:<lens>@<claim_id>` for a rostered lens that left **no trace** on a claim it was
expected on (neither a verdict nor a `record_lens_error` — an error counts as a trace) and
`roster-inconsistency:<lens>@<claim_id>` for a lens that left a trace on a claim it was **not**
expected on. Each of those is INDETERMINATE, never PASS — unknown coverage is not full coverage. The
only opt-out is an **explicitly empty roster** (no `mandatory`, no `conditional`), which declares "no
lens policy asserted" out loud; skipping the call is not an opt-out, it is a defect.

### Step 1 — Fan out

For each rostered verdict lens, `delegate` an **isolated** sub-session (`context_depth="none"`) that
reads the ledger claims + the neutral digest and records a verdict per claim to the ledger
(`claim_ledger record_verdict`). **No lens sees another lens's output** — independence is the whole
point. Launch them concurrently.

**Embed the `run_id` in every lens instruction (hard rule).** Because each lens starts cold
(`context_depth="none"`), it knows only what you write in the instruction. Every delegation MUST
state, verbatim: *"Record each verdict via `claim_ledger record_verdict` with
`run_id="<the exact run_id from Phase 0>"`."* A lens that calls `record_verdict` without it errors
out and its verdict is **lost** — the claim silently stays `PENDING`. Do not paraphrase the run_id,
do not tell the lens to "use the current run" — paste the literal id string.

**Verify coverage before you aggregate.** After the fan-out, read the ledger
(`claim_ledger list_claims`) and confirm **no rostered claim is still `PENDING` for lack of a
recorded verdict.** A claim a lens was supposed to cover but that is still `PENDING` means a verdict
was lost (almost always a missing/`null`/empty `run_id`). Re-run that lens with the literal `run_id`
embedded **before** calling `report` — an unverified claim must never be silently folded into a PASS.

Each verdict is exactly one of `{CONFIRMED, REFUTED, UNTESTABLE, N/A}`, and the ledger **rejects any
CONFIRMED/REFUTED without a `file:line` anchor.**

**empirical-verifier is the exception in kind, not in rule.** It records the same verdict vocabulary
and the same `file:line` anchor as everyone else, but its evidence additionally carries **EMPIRICAL
evidence — the exact command it ran and the output it observed.** It uses a DTU **only if one is
available** in the session and a lighter check cannot settle the claim; otherwise it runs the shipped
test, a minimal repro, or the real call directly. If it could not actually execute anything, it must
record **N/A** ("could not execute: …") — never a CONFIRMED. A read-only opinion from this lens is
not an empirical verdict.

**Fail loud — and record the failure, don't just narrate it.** If a lens errors or returns no
structured verdict, report it prominently ("chokepoint-mapper did not return on claims 3, 7 —
results incomplete") **and record it to the ledger yourself via `claim_ledger record_lens_error`**
(the lens/claim it failed on, plus the error) — because a crashed lens **cannot record its own
failure** (the classic case: the lens spawned without the `claim_ledger` tool and raised
`Tool 'claim_ledger' not found`, so both its verdicts vanished with nothing in the ledger). Recording
the lens error is what makes the gap visible to **gate limb 4** (`lens-error:<lens>@<claim_id>` →
INDETERMINATE) instead of a silently-missing verdict. No synthetic stand-in, no silent drop. A
missing result is INDETERMINATE, never CONFIRMED.

> Every bench lens is granted the `claim_ledger` tool in its own agent frontmatter, so a
> tool-absence crash should not happen; but if it ever does (a broken composition), the concierge
> recording `record_lens_error` is the backstop that keeps the gate from reading clean over a lost
> verdict.

Emit the **roster manifest**: who ran, who was excluded and why.

---

## Phase 4: Aggregate (deterministic — the tool decides)

Call **`claim_ledger report`** — a **single** call that returns the gate verdict *and* the rendered
matrix together (do not make separate `gate` + `render_matrix` calls here). It computes **worst-wins**
aggregation (`REFUTED > UNTESTABLE > CONFIRMED > N/A`) and the BLOCK/PASS/INDETERMINATE verdict.
**Do not re-weigh or soften the result in prose.** Print the matrix and the coverage line verbatim.
This is the divergence from a design council: the gate verdict is data + a mechanical rule, not an
LLM's judgment — so an LLM never assembles it.

**Read `advisory_reasons`, and say what it means.** A run whose `probe_scope` is `"out-of-scope"` (a
**static-only** run — what the `verify-claims` MVP declares) never had the mandate to gather dynamic
adverse-state evidence, so a safety claim with no adverse-state test does **not** block it. Instead
the gate lists it on **`advisory_reasons`** as `unprobed-safety-claim:<claim_id>` — reported, counted
in `coverage.advisory`, and deliberately not folded into the verdict. Surface those advisories
plainly: they are **unprobed safety claims, not cleared ones.** The default `probe_scope: "in-scope"`
is unchanged — there the same gap blocks as `no-adverse-state-test` (limb 2). A waiver clears the
limb identically under either scope.

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

2. **Rounds 2…N (cross-examination), capped at `max_rounds`.** Re-convene **only the lenses party to
   an open item** — a lens holding an unresolved REFUTED, a lens on either side of a direct conflict,
   or a lens whose verdict bears on an UNTESTABLE under adjudication. **Recompute the party set at the
   start of every round:** a finding surfaced in round *N* can pull a previously-quiet lens back in
   (e.g. correspondence-auditor conceding a path makes chokepoint-mapper's CONFIRMED newly load-
   bearing). A lens with no stake in any open item is **not re-invoked**, and its Round-1 verdict
   stands unchanged — silence is not concession, it is an untouched verdict.

   **This scopes *which* lenses run — never *what* a re-convened lens sees.** For every lens you DO
   re-convene: a fresh isolated sub-session (`context_depth="none"`) — which means **the same
   `run_id`-embedding rule from Phase 3 applies again: paste the literal `run_id` into every
   re-convened lens's instruction**, or its revised verdict is lost — and **inject ALL other lenses'
   verbatim last-words, NO concierge curation.** Relay everything; never pre-select what is
   "relevant" — curating reintroduces the silent-filtering risk the design rejects. Record the
   relayed payloads to the ledger (`claim_ledger record_debate`) so the relay is auditable. Ask each
   lens to **hold / revise / concede — in its own voice, with reasons.**

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
   as blockers. **Never downgrade a REFUTED** — that rule binds *your own synthesis judgment* (and
   any lens's): no amount of interpretation, weighing, or softening prose may turn a REFUTED into
   something lesser in the write-up. It is **distinct from the sanctioned `waive` op**, which under
   the `blocking-with-waiver` policy *can* clear a REFUTED — but only as a policy-gated, audited
   **human** decision recorded on the ledger with an explicit `by` + `reason`. A waiver is a decision
   made in the open and attributable; a downgrade is you quietly deciding the finding matters less.
   You may interpret and weigh; dissent stays visible.
   - **Group REFUTED claims that share ONE counter-case into ONE root defect.** When several REFUTED
     claims are refuted by the *same* counter-case (the same unguarded path, the same off-by-one, the
     same missing await), present them as a **single root defect** with its counter-case stated once
     and the member claim IDs listed beneath it — not as N independent blockers that read like N
     separate bugs. This is **presentation only**: the gate data is untouched, every REFUTED still
     blocks, every member claim ID stays individually visible and individually resolvable, and the
     counts you quote from `blocking_summary` remain the tool's. Claims with **different**
     counter-cases are **never** merged — sharing a file, a symbol, or a theme is not sharing a
     counter-case. Grouping is a reading aid for the human; it never reduces the blocker count.
   - A **`no-adverse-state-test`** blocker (limb 2) and an **`UNTESTABLE`** claim are not dead ends:
     they route to the **Phase-2 probe pipeline** — `probe-designer` → `pen-tester` →
     `regression-graduator`. Those agents record through the Phase-2 ledger ops, **not**
     `record_verdict`: `record_probe` (attaches the probe, increments `coverage.probed`),
     `graduate_test` (promotes a surviving probe into a committed standing test — the op that
     actually clears limb 2), and `defer_claim` (marks a not-yet-probed eligible claim; deferred ≠
     passed, still trips the gate). Hand each Phase-2 agent the **literal `run_id`**, exactly as for
     a lens. A probe recorded only via `record_verdict` leaves `coverage.probed == 0` and the block
     un-closed — that is the wrong door.
   - **Separate substantive from procedural blockers — do not present an undifferentiated wall.** The
     `report` result carries `blocking_summary` (`{substantive, procedural, total_claims_blocked}`)
     and tags each blocked claim with a `category`. Present the **substantive** blockers first —
     `category: "substantive"` (a `REFUTED` claim: the claim is actually *false*, the real defect) —
     then the **procedural** ones grouped separately — `category: "procedural"` (only
     `no-adverse-state-test` and/or `UNTESTABLE-unwaived`: the claim may be true but its *evidence
     artifact* is missing). A run blocked ONLY by procedural entries is a different message to the
     human than one with a false claim; say which it is, and lead with the count from
     `blocking_summary`. Each blocked claim now appears **once** with its limbs grouped in `reasons`
     — never re-list the same claim per limb.
   - **The procedural remediations, explicitly:** `no-adverse-state-test` → run the Phase-2 probe
     pipeline above (a graduated test clears it). `UNTESTABLE-unwaived` → either make it decidable via
     Phase-2, or **waive it with a reason** via `claim_ledger waive` (claim_id + reason). A waiver is
     an **auditable caller decision made in the open** — never an auto-downgrade you perform silently.
     **Know the tool's actual reach (do not assume the ratchet protects you here):** under the default
     `blocking-with-waiver` policy a waiver clears **any** limb of the claim it names — **including a
     `REFUTED`** — because `waive` does not inspect the claim's aggregate. Nothing in the tool stops a
     waiver from silently clearing a *false* claim; that guard is a discipline you enforce, not a rule
     the ledger enforces (tracked for hardening as a tool gap). Therefore: **only ever waive a
     procedural block; never waive a `REFUTED` to make a false claim disappear.** If a run genuinely
     must not allow waivers to clear a block at all, gate it under the `blocking` policy. And per the
     combined-flow rule, if you authored a claim, you are not also its sole waiver — surface the waive,
     with its reason, to a human.
4. **Attribute every finding to a named lens** and **quote at least one verbatim line per lens.** No
   anonymous synthesis.
5. **Keep REFUTED, UNTESTABLE, and N/A distinguishable** — a blocker must never be confused with an
   abstention or an untestable.
6. End with the standing tradeoffs stated plainly for the human, and (for BLOCKs) the proposed
   counter-cases and one-line fixes the lenses surfaced.

Remember the recursive lesson: a gate that manufactures confidence is worse than none. If coverage
is incomplete, say **INDETERMINATE** — do not present a partial run as a clean pass.

---

## Phase 7: Close-out — a harvested run must never be silently abandoned

The single most common real-world failure of this gate is **not** a wrong verdict — it is a run that
gets **harvested and then evaporates**: claims recorded in Phase 2, and the session moves on to
other work without ever reaching a gate. The claims sit `PENDING` forever; the run is a silent
orphan. **Harvesting a run is a commitment to gate it.**

**Before you end this session, hand off, or move on to unrelated work, run the close-out check —
every time:**

1. **This run.** Read it back: `claim_ledger list_claims` for your `run_id`. If **any** claim is
   still `PENDING` (no verdict), the run is **not done** — you either finish the fan-out (Phase 3)
   and reach a `report` verdict, or you **explicitly abandon** the run and say so out loud (why, and
   what a resumer would need). A `PENDING` claim you walk away from without a word is the failure
   this phase exists to stop.
2. **Every run in this repo.** `claim_ledger list_runs` with `stranded_only=true` returns every run
   that has claims but is not fully verdicted (`stranded == claims>0 and pending>0`), plus a
   `stranded_count`. **A non-zero `stranded_count` at close-out is a loud stop, not a footnote** —
   for each stranded run, resolve it (gate it), or record an explicit, resumable abandonment.
   *(Best-effort today: `list_runs` flags a run as stranded on un-verdicted claims. Exact "harvested
   but the gate was never invoked" detection is tracked separately — but an un-verdicted claim is
   already the dominant abandonment signature.)*

**Never present a run as finished, and never let a session end, while a run you touched is stranded.**
If you hold a work-tracker item bound to this run, this close-out is a precondition for
`work_resolve` — see the `work-tracker-with-claim-guard` skill's session-end stranded-state
checklist, of which this is the claim-guard half.
