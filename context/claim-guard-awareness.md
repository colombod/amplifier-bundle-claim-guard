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
- **Agent path (load this):** the **`claim-guard-here`** skill — the concierge playbook (cold
  fan-out → debate → synthesis with recorded dissent), run inline in this session. **Load it
  BEFORE touching the `claim_ledger` tool.** Driving `claim_ledger` op-by-op without the playbook
  produces an unattributed, ungated result.
- **Human path:** `/claim-guard <changeset>` — activates the claim-guard posture
  (`write_file`/`edit_file` blocked) and starts the playbook on that changeset.
- **Isolated run:** `/claim-guard-review <changeset>` — the same gate in a forked session.
- **Pipeline (optional):** `claim-guard:recipes/verify-claims.yaml`, when the `recipes` tool is
  present.

**The gate never edits the code under review.** Activate the `/claim-guard` mode to enforce this
(`write_file`/`edit_file` blocked). The gate rule and the claim-verification matrix are computed
deterministically by the `claim_ledger` tool — never by an LLM. The ledger's on-disk form is
**private** — read it via `claim_ledger list_claims` (or `claim_ledger report`), never by opening
`.claim-guard/` directly.
