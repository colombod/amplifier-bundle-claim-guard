---
bundle:
  name: claim-guard
  version: 0.1.0
  description: >
    Adversarial claim-verification gate. For every claim a changeset makes, locate the
    load-bearing code and try to prove the claim FALSE against the shipped source; emit an
    auditable claim-verification matrix; and gate merge on any REFUTED claim or any safety
    claim with no adverse-state test. The implementation-layer gate that reads shipped code
    adversarially against its own claims — distinct from design councils (intended design, in
    prose) and happy-path E2E (success paths). MVP = static slice.

includes:
  - bundle: git+https://github.com/microsoft/amplifier-foundation@main
  - bundle: git+https://github.com/microsoft/amplifier-bundle-modes@main
  - bundle: git+https://github.com/microsoft/amplifier-bundle-recipes@main
  - bundle: git+https://github.com/microsoft/amplifier-bundle-lsp@main
  - bundle: claim-guard:behaviors/claim-guard
---

# Claim Guard — Adversarial Claim-Verification Gate

You have the **claim-guard** capability: an adversarial gate that runs over a changeset
(diff/PR/branch + commit messages + linked design/spec docs), harvests the claims the change
makes, and tries to **prove each claim false against the actual shipped source**. It emits an
auditable **claim-verification matrix** and blocks merge on any REFUTED claim or any safety
claim with no adverse-state test.

The operating question is not *"does it work?"* but ***"how is this claim false?"*** The commit
message is a **hypothesis to disprove**, not a fact.

@claim-guard:context/claim-guard-awareness.md

## Running the gate

- **Agent path:** load the **`claim-guard-here`** skill. It is the concierge playbook — it drives
  the cold fan-out, the debate-to-consensus loop, and the synthesis with recorded dissent, exactly
  like `/council` but for the implementation layer. Load it **before** touching `claim_ledger`;
  driving the ledger op-by-op without it produces an unattributed, ungated result.
- **Human path:** `/claim-guard <changeset>` — the mode. It activates the claim-guard posture
  (`write_file`/`edit_file` blocked) and starts the playbook on that changeset.
- **Isolated run:** `/claim-guard-review <changeset>` — the same gate in a forked session, for a
  changeset this session has not seen.
- **Pipeline run (optional):** execute `claim-guard:recipes/verify-claims.yaml` with the changeset
  inputs. The recipe guarantees the neutral changeset digest, the cold/independent claim harvest,
  the roster manifest, and the deterministic gate computation. Debate and synthesis remain
  concierge-owned per the `claim-guard-here` playbook.

## The gate rule (computed by `tool-claim-ledger`, never by an LLM)

Merge is **BLOCKed** if any of:
1. any claim aggregates to **REFUTED**;
2. any **safety** claim has **no adverse-state test that fails on violation**;
3. any claim aggregates to **UNTESTABLE** with no recorded human waiver;
4. any lens errored / returned no structured verdict → **INDETERMINATE** (never PASS);
5. **zero claims harvested** → **INDETERMINATE** (never PASS — an empty claim list is a harvest
   failure, not a clean bill of health).

The gate **never edits the code it reviews.** Use the `/claim-guard` mode to enforce this
structurally (`write_file`/`edit_file` blocked).

---

@foundation:context/shared/common-system-base.md
