---
name: claim-harvesting
description: "The discipline of extracting the load-bearing claims a changeset makes — explicit (commits, PR, docs, and highest-yield docstrings/comments) and implicit (what the change exists FOR, even unstated). Use when harvesting or typing claims for the claim-guard gate, or whenever you need to turn a change into a checklist of assertions to verify."
model_role: reasoning
---

# Claim Harvesting

A claim you never wrote down is a claim nothing will verify. Harvesting is the load-bearing first
move of the gate: its output bounds everything downstream. Every escaped blocker in the incident
that motivated this bundle was a place where a *belief* — stated or merely held — was confidently
false.

## Two harvests, UNIONed never intersected

- **Explicit** (`claim-harvester`): what the change *says* it does.
- **Implicit** (`purpose-inquisitor`): what the change *exists for*, even when unstated.

Run them **cold and independent**, then UNION. Inference can only **add** claims; it can never
remove one the explicit harvest found. Intersection would silently drop the most valuable claims —
the implicit safety ones nobody wrote down.

## Explicit sources, in yield order

1. **Docstrings and inline comments in the changed code — HIGHEST YIELD.** Comments encode the
   author's *belief*. `# idempotent MERGE makes replay a no-op` is a claim. The confidently-false
   comment sits right next to the wrong line more often than anywhere else.
2. **Commit messages** — the change's own summary.
3. **PR / branch description** — the narrative told to reviewers.
4. **Linked design / spec docs** — the promises the change was meant to keep.

Read the actual sources (`git log`, `git diff`, `read_file`, `grep`). Never reason from priors about
what a change "probably" claims.

## Implicit inference: from purpose to promised property

For each change ask, in order:
1. **What breaks in the world if this change didn't exist?** → the condition it manages.
2. **What must stay true while that condition is handled?** → the implicit claim.
3. **Is that a safety/integrity property** (corruption / loss / inversion / staleness)? → then it is
   almost certainly load-bearing and almost certainly untested (tests covered the liveness the
   commit mentioned, not the integrity the change was *for*).

Ground every inferred claim in a specific **basis** (the exact thing you derived it from). A prior
design-council verdict is a rich source: each addressed FAIL/CONCERN is an implicit claim that "the
concern was handled in the code" — exactly the promises made in prose and under-delivered in source.

## What counts as load-bearing

Keep claims whose falseness would matter: guarantees, prevention, bounds, invariants, coverage.
Discard prose that asserts nothing testable ("cleaned up", "improved readability").

## The claim contract (shared source of truth — both harvesters obey it)

> This is the **single contract** the `claim-harvester` and `purpose-inquisitor` both follow, and it
> is co-designed with the ledger's `normalize_text` (the stable-`claim_id` hash, F-9). It exists so
> the *same* underlying claim decomposes and phrases the *same* way every run — otherwise it hashes
> to a different id and the run-to-run matrix diff breaks (KI-1). **Do not let this drift from the
> normalizer:** the boilerplate you omit here is exactly what the normalizer strips; the
> meaning-critical words you keep here are exactly what it preserves.

### Granularity — one load-bearing assertion per claim (kills count variance)

Decompose the change **deterministically, not by mood.** The claim count is a function of
**(distinct mechanism × distinct forbidden-property)** in the change — *not* of how you happen to
phrase it this run.

- **Atomicity test — the decisive rule:** *"Can ONE counter-case falsify exactly this claim and
  nothing else?"* If yes → it is one claim. If falsifying it takes **two independent counter-cases**
  → **split**.
- **SPLIT when** a candidate names two distinct mechanisms/symbols, OR conjoins two independently
  verifiable properties ("gates writes **and** self-clears" → two claims), OR mixes two forbidden
  violation classes (corruption vs staleness).
- **MERGE (do not split) when** the parts cannot be refuted independently — a single mechanism whose
  single load-bearing line enforces one property is **one** claim even if the sentence is compound
  ("reads `schema_health` and refuses the write" is one gate = one claim).
- **One claim per (mechanism × property).** Property ∈ {corruption, loss, inversion, staleness,
  bound/quantity, idempotence, coverage}. Enumerate the change's mechanisms and the property each
  must hold; **that grid IS the claim set.** Build the grid before you write any claim text.

### Canonical claim-statement form (kills phrasing variance)

Write every claim's `text` in this exact shape, so trivially-different wordings converge to one id:

- **One declarative sentence, `<subject> <predicate> <object/condition>`, present tense, active
  voice.** ("the write path reads `schema_health` before writing" — *not* "`schema_health` will be
  read by the write path before writes occur").
- **Name the load-bearing symbol/mechanism in the text** — `max_delete`, `schema_health`,
  `_handle_exhausted_batch`. Symbols are line-stable, high-signal discriminators that keep distinct
  claims distinct.
- **Put the `file:line` in the `source` field, not the text.** `source` already handles line drift;
  keep line refs out of the sentence.
- **No boilerplate lead-ins.** Never start with "the code ensures that…", "this change guarantees…",
  "the system will…". **Start with the subject.** *(These lead-ins are exactly what the normalizer
  strips — so writing them changes nothing but risks meaning drift; omit them.)*
- **Controlled vocabulary for the meaning-critical words** (the normalizer deliberately does NOT fold
  these, so you must standardize them here):
  - **negation:** use `no` / `not` / `never` / `cannot` — never "won't", "isn't", "doesn't";
  - **bounds:** use `at most N` / `at least N` / `exactly N` / `under N` — never "no more than",
    "up to";
  - **singular head noun** for the violated property: "no duplicate `Node` is created" — never
    "no duplicate Nodes are created";
  - prefer the **mechanism's own verb** — `gate`, `validate`, `reject`, `refuse` — over loose
    synonyms ("blocks", "stops", "checks").

**Worked example (canonical form ↔ normalizer agreement).** Two authors, same claim:
"The code ensures that `max_delete` is a cap." and "`max_delete` is a cap" — both must be written
canonically as **`max_delete` caps deletes** (subject-first, symbol named, no boilerplate). The
normalizer then maps both to the same id: it strips the `the code ensures that` boilerplate and the
`is a`/article fillers, leaving one stable hash. Emit the canonical form and the agreement is
automatic; emit boilerplate and you rely on the normalizer to undo it, which is fragile.

## Typing — and the safety bias (F-8)

Type each claim: `correspondence | safety | quantitative | temporal | concurrency | coverage`. The
type drives lens routing, probe eligibility, and the gate's second limb.

**Bias toward `safety`:** when a claim contains prevention/integrity language — *prevent, cannot,
won't, never, no <bad thing>, guard, ensure no, refuse* — default it to `safety`. A false `safety`
costs one extra probe; a safety claim mistyped as `correspondence` silently escapes the strongest
gate limb. Bias toward the stricter limb.

## The zero-claim rule (S-8)

If you find no claims, say so explicitly — never invent them. A zero-claim harvest becomes an
**INDETERMINATE** gate result, never a PASS. An empty checklist is a harvest failure, not a clean
bill of health. Note where you looked so the human can supply a commit message or linked doc.
