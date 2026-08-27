"""Worst-wins aggregation -- deterministic, never an LLM.

REFUTED > UNTESTABLE > CONFIRMED > N/A

A claim with zero recorded verdicts is PENDING (a gap must never read as a pass).
"""

from __future__ import annotations

from typing import Any

from .roster import compute_roster_coverage

_PRECEDENCE = {"REFUTED": 3, "UNTESTABLE": 2, "CONFIRMED": 1, "N/A": 0}


def compute_aggregate(verdicts: list[dict]) -> str:
    """Compute the worst-wins aggregate over a claim's (one-per-lens) verdict records.

    - Any single REFUTED -> REFUTED. A CONFIRMED from another lens cannot raise it.
    - No REFUTED but any UNTESTABLE -> UNTESTABLE.
    - All present verdicts CONFIRMED (with >=1) -> CONFIRMED.
    - Only N/A -> N/A. An abstention never lowers an aggregate.
    - No verdicts at all -> PENDING.
    """
    if not verdicts:
        return "PENDING"

    best_verdict = "N/A"
    best_rank = -1
    for record in verdicts:
        rank = _PRECEDENCE.get(record["verdict"], -1)
        if rank > best_rank:
            best_rank = rank
            best_verdict = record["verdict"]
    return best_verdict


def compute_coverage(
    claims: list[dict], roster: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Coverage summary used by both `aggregate` and `gate` operations.

    `lens_expected`/`lens_covered` are `None` (never `0`) when no roster has
    been declared for the run -- `0/0` would render as "complete" to a human
    skimming the coverage line; `n/a` does not (see `roster.py`).
    """
    harvested = len(claims)
    verified = sum(1 for c in claims if c.get("aggregate") != "PENDING")
    probed = sum(1 for c in claims if c.get("probe") is not None)
    deferred = sum(1 for c in claims if c.get("probe_eligibility") == "deferred")
    waived = sum(1 for c in claims if c.get("waiver") is not None)
    roster_coverage = compute_roster_coverage(claims, roster)
    return {
        "harvested": harvested,
        "verified": verified,
        "probed": probed,
        "deferred": deferred,
        "waived": waived,
        "lens_expected": roster_coverage["lens_expected"],
        "lens_covered": roster_coverage["lens_covered"],
    }
