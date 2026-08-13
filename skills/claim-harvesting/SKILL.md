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
