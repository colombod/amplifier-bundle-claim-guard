"""Roster-derived expected-lens coverage (closes the silent lens-coverage hole).

See docs/tool-claim-ledger-contract.md "declare_roster". This module is
deliberately separate from `aggregate.py` -- worst-wins aggregation and roster
coverage are different concerns with different inputs (one brick, one job).

The roster is a POLICY declared once per run (`{mandatory: [...], conditional:
{<lens>: {types, included, reason}}}`). `expected_lenses` is a PURE function of
`(claim.type, roster)` -- derived lazily, never persisted per claim, so a
Gate-A retype of a claim's `type` automatically re-routes its expected lenses
on the very next `aggregate`/`gate`/`render_matrix` call. This module never
learns what any lens *means* -- only that some lens name is expected on some
claim types, per the policy data the caller supplied.
"""

from __future__ import annotations

from typing import Any

CLAIM_TYPES: frozenset[str] = frozenset(
    {"correspondence", "safety", "quantitative", "temporal", "concurrency", "coverage"}
)


def expected_lenses(claim: dict[str, Any], roster: dict[str, Any] | None) -> list[str]:
    """The lenses expected to report on `claim`, per `roster`. Sorted; [] when
    `roster` is None (undeclared roster expects nothing -- see `no-roster-declared`
    at the gate, which is a separate, run-level signal from this per-claim result).
    """
    if roster is None:
        return []
    expected: set[str] = set(roster.get("mandatory") or [])
    claim_type = claim.get("type")
    for lens, cond in (roster.get("conditional") or {}).items():
        if cond.get("included") and claim_type in (cond.get("types") or []):
            expected.add(lens)
    return sorted(expected)


def covered_lenses(claim: dict[str, Any]) -> set[str]:
    """Lenses that left a trace on `claim` -- a recorded verdict OR a recorded
    lens error. A lens error counts as covered (it left a trace); see the
    contract's rationale for why this is load-bearing and never conflated with
    a coverage gap.
    """
    verdict_lenses = {v["lens"] for v in claim.get("verdicts") or []}
    error_lenses = {e["lens"] for e in claim.get("lens_errors") or []}
    return verdict_lenses | error_lenses


def compute_roster_coverage(
    claims: list[dict[str, Any]], roster: dict[str, Any] | None
) -> dict[str, Any]:
    """Single source of truth consumed by the gate, the coverage counters, and
    the matrix -- one computation, three renderings.
    """
    if roster is None:
        return {
            "declared": False,
            "gaps": [],
            "inconsistencies": [],
            "lens_expected": None,
            "lens_covered": None,
        }

    # The empty-roster opt-out: a roster with NEITHER a mandatory lens NOR any
    # conditional entry asserts no policy at all -- gaps and inconsistencies
    # are both vacuous by declaration, not merely by an empty expected set. A
    # non-empty roster (even a single mandatory lens) makes coverage tracking
    # live, and any lens outside its per-claim expected set that leaves a
    # trace is a real roster-inconsistency.
    is_empty_roster = not (roster.get("mandatory") or roster.get("conditional"))
    if is_empty_roster:
        return {
            "declared": True,
            "gaps": [],
            "inconsistencies": [],
            "lens_expected": 0,
            "lens_covered": 0,
        }

    gaps: list[dict[str, str]] = []
    inconsistencies: list[dict[str, str]] = []
    lens_expected_total = 0
    lens_covered_total = 0

    for claim in claims:
        claim_id = claim["claim_id"]
        expected = set(expected_lenses(claim, roster))
        covered = covered_lenses(claim)

        lens_expected_total += len(expected)
        lens_covered_total += len(expected & covered)

        for lens in expected - covered:
            gaps.append({"lens": lens, "claim_id": claim_id})
        for lens in covered - expected:
            inconsistencies.append({"lens": lens, "claim_id": claim_id})

    gaps.sort(key=lambda g: (g["claim_id"], g["lens"]))
    inconsistencies.sort(key=lambda i: (i["claim_id"], i["lens"]))

    return {
        "declared": True,
        "gaps": gaps,
        "inconsistencies": inconsistencies,
        "lens_expected": lens_expected_total,
        "lens_covered": lens_covered_total,
    }


def validate_roster(payload: dict[str, Any]) -> str | None:
    """Validate a `declare_roster` payload. Returns None when valid, else a
    human-readable rejection message (see the contract's `declare_roster`
    validation table). Never mutates `payload`.
    """
    mandatory = payload.get("mandatory")
    if not isinstance(mandatory, list) or not all(
        isinstance(item, str) and item for item in mandatory
    ):
        return "mandatory must be an array of lens names"

    conditional = payload.get("conditional")
    if conditional is None:
        conditional = {}
    if not isinstance(conditional, dict):
        return "conditional must be an object keyed by lens name"

    for lens, cond in conditional.items():
        if not isinstance(cond, dict) or not isinstance(cond.get("included"), bool):
            return (
                f"conditional[{lens}] requires types (array), included (bool), "
                "and reason"
            )
        reason = cond.get("reason")
        if not isinstance(reason, str) or not reason:
            return (
                f"conditional[{lens}] requires types (array), included (bool), "
                "and reason"
            )
        types = cond.get("types")
        if not isinstance(types, list):
            return (
                f"conditional[{lens}] requires types (array), included (bool), "
                "and reason"
            )
        for claim_type in types:
            if claim_type not in CLAIM_TYPES:
                return (
                    f"conditional[{lens}].types contains unknown claim type: "
                    f"{claim_type} (valid: {sorted(CLAIM_TYPES)})"
                )

    duplicate = set(mandatory) & set(conditional.keys())
    if duplicate:
        lens = min(duplicate)
        return f"{lens} appears in both mandatory and conditional"

    return None
