"""The gate rule -- deterministic, pure computation over the ledger.

See docs/tool-claim-ledger-contract.md "The gate rule (deterministic)".

verdict = BLOCK if any:
  1. any claim aggregate == REFUTED
  2. any safety claim has adverse_state_test.exists == false (independent of limb 1)
     -- but ONLY when the run's `probe_scope` is "in-scope" (the default). A run
     that declares `probe_scope: "out-of-scope"` (a static-only run, e.g. the
     `verify-claims` MVP) never had the mandate to gather dynamic adverse-state
     evidence, so this limb does not block it: the claim is instead surfaced as
     an advisory reason "unprobed-safety-claim:<claim_id>" on the new
     `advisory_reasons` list, and never affects the verdict. Waiver behavior is
     unchanged in BOTH modes -- a waived safety claim clears this limb either way.
  3. any claim aggregate == UNTESTABLE with no recorded `waiver` (policy-dependent)

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
  4c. (roster coverage, additive -- see roster.py) a rostered lens left no trace
     (no verdict, no lens error) on a claim it was expected on --
     "lens-coverage-gap:<lens>@<claim_id>"; or a lens left a trace on a claim it
     was NOT expected on -- "roster-inconsistency:<lens>@<claim_id>"; or the run
     harvested claims but never declared a roster -- "no-roster-declared" (an
     undeclared roster is unknown coverage, not full coverage; suppressed when
     harvested == 0, since zero-claims-harvested already covers that run).
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
from .roster import compute_roster_coverage

_POLICIES = {"advisory", "blocking-with-waiver", "blocking"}
_SAFETY_TYPES = {"safety"}
_PROBE_SCOPES = {"in-scope", "out-of-scope"}


def compute_gate(run_record: dict[str, Any], gate_policy: str) -> dict[str, Any]:
    claims = run_record.get("claims", [])
    harvested = len(claims)
    roster = run_record.get("roster")
    probe_scope = run_record.get("probe_scope") or "in-scope"

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

    # Limb 4c -- roster coverage (additive; see roster.py). Never touches limbs
    # 1-3 or worst-wins: a coverage gap turns the RUN into INDETERMINATE, it
    # never rewrites a claim's aggregate.
    roster_coverage = compute_roster_coverage(claims, roster)
    if harvested > 0 and not roster_coverage["declared"]:
        indeterminate_reasons.append("no-roster-declared")
    for gap in roster_coverage["gaps"]:
        indeterminate_reasons.append(
            f"lens-coverage-gap:{gap['lens']}@{gap['claim_id']}"
        )
    for inconsistency in roster_coverage["inconsistencies"]:
        indeterminate_reasons.append(
            f"roster-inconsistency:{inconsistency['lens']}@{inconsistency['claim_id']}"
        )

    def waived_clears(claim: dict[str, Any]) -> bool:
        return claim.get("waiver") is not None and gate_policy == "blocking-with-waiver"

    # Reasons are collected PER claim (claim_id -> ordered list of tripped limb
    # reasons), then flattened into one grouped entry per blocked claim below.
    # This is a presentation-only change: the set of claims that trip any limb,
    # and therefore the BLOCK/PASS/INDETERMINATE verdict, is byte-for-byte
    # identical to the old flat-list logic -- only how those trips are grouped
    # and ordered for the reader changes.
    reasons_by_claim: dict[str, list[str]] = {}
    advisory_reasons: list[str] = []

    def _trip(claim: dict[str, Any], reason: str) -> None:
        reasons_by_claim.setdefault(claim["claim_id"], []).append(reason)

    # Limb 1 -- any REFUTED aggregate.
    for claim in claims:
        if claim.get("aggregate") == "REFUTED" and not waived_clears(claim):
            _trip(claim, "REFUTED")

    # Limb 2 -- safety claim with no adverse-state test. Independent of limb 1: a
    # CONFIRMED safety claim with no adverse-state test still blocks -- but ONLY
    # under probe_scope == "in-scope" (the default). Under "out-of-scope" (a
    # static-only run that never had the mandate to gather dynamic evidence),
    # the same gap is surfaced as an advisory reason instead, and never touches
    # the verdict. Waiver clears this limb identically in both modes.
    for claim in claims:
        if claim.get("type") in _SAFETY_TYPES:
            adverse_state_test = claim.get("adverse_state_test") or {}
            if not adverse_state_test.get("exists") and not waived_clears(claim):
                if probe_scope == "out-of-scope":
                    advisory_reasons.append(
                        f"unprobed-safety-claim:{claim['claim_id']}"
                    )
                else:
                    _trip(claim, "no-adverse-state-test")

    # Limb 3 -- UNTESTABLE with no waiver. Computed regardless of policy so `advisory`
    # can report it; the policy only controls whether it produces a final BLOCK.
    for claim in claims:
        if claim.get("aggregate") == "UNTESTABLE" and not waived_clears(claim):
            _trip(claim, "UNTESTABLE-unwaived")

    # Group into one entry per blocked claim, substantive (REFUTED present)
    # first, then procedural, each in stable claim order -- deterministic.
    claims_by_id = {claim["claim_id"]: claim for claim in claims}
    substantive: list[dict[str, Any]] = []
    procedural: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = claim["claim_id"]
        reasons = reasons_by_claim.get(claim_id)
        if not reasons:
            continue
        entry = {
            "claim_id": claim_id,
            "text": claims_by_id[claim_id]["text"],
            "reasons": reasons,
            "category": "substantive" if "REFUTED" in reasons else "procedural",
        }
        (substantive if entry["category"] == "substantive" else procedural).append(
            entry
        )

    blocking_claims: list[dict[str, Any]] = substantive + procedural
    blocking_summary = {
        "substantive": len(substantive),
        "procedural": len(procedural),
        "total_claims_blocked": len(blocking_claims),
    }

    if indeterminate_reasons:
        verdict = "INDETERMINATE"
    elif blocking_claims and gate_policy != "advisory":
        verdict = "BLOCK"
    else:
        verdict = "PASS"

    coverage = compute_coverage(claims, roster)
    coverage["advisory"] = len(advisory_reasons)

    return {
        "ok": True,
        "run_id": run_record.get("run_id"),
        "verdict": verdict,
        "blocking_claims": blocking_claims,
        "blocking_summary": blocking_summary,
        "indeterminate_reasons": indeterminate_reasons,
        "advisory_reasons": advisory_reasons,
        "coverage": coverage,
    }


def validate_gate_policy(gate_policy: str) -> bool:
    return gate_policy in _POLICIES


def validate_probe_scope(probe_scope: str) -> bool:
    return probe_scope in _PROBE_SCOPES
