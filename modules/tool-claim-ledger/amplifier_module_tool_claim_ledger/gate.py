"""The gate rule -- deterministic, pure computation over the ledger.

See docs/tool-claim-ledger-contract.md "The gate rule (deterministic)".

verdict = BLOCK if any:
  1. any claim aggregate == REFUTED
  2. any safety claim has adverse_state_test.exists == false (independent of limb 1)
  3. any claim aggregate == UNTESTABLE with no waiver (policy-dependent)

verdict = INDETERMINATE (never PASS) if any:
  4. any claim is PENDING (missing verdict), or any lens recorded an error via
     `record_lens_error` -- each is a distinct structural signal that an expected
     lens result is missing or broken, and each is reported with its own reason
     string: "claim-pending:<claim_id>" for a claim with zero recorded verdicts,
     and "lens-error:<lens>@<claim_id>" for a recorded lens error. A claim can
     carry both at once (an unverified claim whose only lens attempt crashed), or
     a lens-error alone even when the claim already has other lenses' verdicts
     (that claim's aggregate is unaffected by the error -- see module docstring
     note below).
  5. zero claims harvested

Otherwise verdict = PASS.

Policy modifiers:
  advisory              -- always compute+report; never returns BLOCK (blocking_claims
                            is still populated so the report is meaningful); INDETERMINATE
                            is never downgraded.
  blocking-with-waiver   -- (default) BLOCK per above; a waiver clears a claim's
                            contribution to limbs 1-3.
  blocking               -- BLOCK per above; waivers are recorded but never clear a block.

Implementation note on limb 4 ("any lens errored / returned no structured verdict, or
any claim is PENDING"): limb 4 is now fully wired. A lens (or the recipe/concierge
driving it) records a crash/error explicitly via `record_lens_error`, which appends a
`lens_errors` entry to the claim -- it never creates a verdict and never touches
`aggregate`/`adverse_state_test`, so a lens error can never be mistaken for a verdict
by limbs 1-3 or by worst-wins. `compute_gate` below surfaces every recorded lens error
as its own `lens-error:<lens>@<claim_id>` indeterminate reason, independent of (and in
addition to) the `claim-pending:<claim_id>` signal for claims with zero verdicts. A
lens crash is only invisible to the gate if the calling recipe/concierge fails to call
`record_lens_error` before invoking `gate` -- that remains the caller's responsibility,
but the ledger itself no longer conflates "not yet verified" with "verification broke".
"""

from __future__ import annotations

from typing import Any

from .aggregate import compute_coverage

_POLICIES = {"advisory", "blocking-with-waiver", "blocking"}
_SAFETY_TYPES = {"safety"}


def compute_gate(run_record: dict[str, Any], gate_policy: str) -> dict[str, Any]:
    claims = run_record.get("claims", [])
    harvested = len(claims)

    indeterminate_reasons: list[str] = []
    if harvested == 0:
        indeterminate_reasons.append("zero-claims-harvested")
    for claim in claims:
        if claim.get("aggregate") == "PENDING":
            indeterminate_reasons.append(f"claim-pending:{claim['claim_id']}")
        for lens_error in claim.get("lens_errors") or []:
            indeterminate_reasons.append(
                f"lens-error:{lens_error['lens']}@{claim['claim_id']}"
            )

    def waived_clears(claim: dict[str, Any]) -> bool:
        return claim.get("waiver") is not None and gate_policy == "blocking-with-waiver"

    blocking_claims: list[dict[str, str]] = []

    # Limb 1 -- any REFUTED aggregate.
    for claim in claims:
        if claim.get("aggregate") == "REFUTED" and not waived_clears(claim):
            blocking_claims.append(
                {
                    "claim_id": claim["claim_id"],
                    "text": claim["text"],
                    "reason": "REFUTED",
                }
            )

    # Limb 2 -- safety claim with no adverse-state test. Independent of limb 1: a
    # CONFIRMED safety claim with no adverse-state test still blocks.
    for claim in claims:
        if claim.get("type") in _SAFETY_TYPES:
            adverse_state_test = claim.get("adverse_state_test") or {}
            if not adverse_state_test.get("exists") and not waived_clears(claim):
                blocking_claims.append(
                    {
                        "claim_id": claim["claim_id"],
                        "text": claim["text"],
                        "reason": "no-adverse-state-test",
                    }
                )

    # Limb 3 -- UNTESTABLE with no waiver. Computed regardless of policy so `advisory`
    # can report it; the policy only controls whether it produces a final BLOCK.
    for claim in claims:
        if claim.get("aggregate") == "UNTESTABLE" and not waived_clears(claim):
            blocking_claims.append(
                {
                    "claim_id": claim["claim_id"],
                    "text": claim["text"],
                    "reason": "UNTESTABLE-unwaived",
                }
            )

    if indeterminate_reasons:
        verdict = "INDETERMINATE"
    elif blocking_claims and gate_policy != "advisory":
        verdict = "BLOCK"
    else:
        verdict = "PASS"

    coverage = compute_coverage(claims)

    return {
        "ok": True,
        "run_id": run_record.get("run_id"),
        "verdict": verdict,
        "blocking_claims": blocking_claims,
        "indeterminate_reasons": indeterminate_reasons,
        "coverage": coverage,
    }


def validate_gate_policy(gate_policy: str) -> bool:
    return gate_policy in _POLICIES
