# Claim Guard — awareness

An **adversarial claim-verification gate** is available. It runs over a changeset (diff/PR/branch
+ commit messages + linked design/spec docs) and, for every claim the change makes, tries to
**prove that claim false against the actual shipped source** — then blocks merge on any REFUTED
claim or any safety claim with no adverse-state test.

It is the **implementation-layer** gate: it reads shipped code adversarially against its own
promises. Distinct from design councils (which reason about intended design, in prose) and
happy-path E2E (which proves success paths). The question is not *"does it work?"* but
***"how is this claim false?"***

**To run it:**
- `/claim-guard` skill — the concierge playbook (cold fan-out → debate → synthesis with recorded
  dissent). This is the interactive path.
- `claim-guard:recipes/verify-claims.yaml` — the staged pipeline path.

**The gate never edits the code under review.** Activate the `/claim-guard` mode to enforce this
(`write_file`/`edit_file` blocked). The gate rule and the claim-verification matrix are computed
deterministically by the `claim_ledger` tool — never by an LLM.
