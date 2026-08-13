"""Worst-wins aggregation: every precedence pair, especially CONFIRMED+REFUTED->REFUTED
(the S-3 case) and the missing-lens->PENDING case.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.aggregate import (
    compute_aggregate,
    compute_coverage,
)


def _verdict(lens: str, verdict: str) -> dict:
    return {
        "lens": lens,
        "verdict": verdict,
        "evidence": [],
        "counter_case": None,
        "round": 1,
        "recorded_at": "x",
    }


def test_no_verdicts_is_pending() -> None:
    assert compute_aggregate([]) == "PENDING"


def test_single_confirmed() -> None:
    assert (
        compute_aggregate([_verdict("correspondence-auditor", "CONFIRMED")])
        == "CONFIRMED"
    )


def test_single_refuted() -> None:
    assert (
        compute_aggregate([_verdict("correspondence-auditor", "REFUTED")]) == "REFUTED"
    )


def test_single_untestable() -> None:
    assert compute_aggregate([_verdict("pen-tester", "UNTESTABLE")]) == "UNTESTABLE"


def test_single_na() -> None:
    assert compute_aggregate([_verdict("boundary-adversary", "N/A")]) == "N/A"


def test_confirmed_cannot_raise_a_refuted_the_s3_case() -> None:
    """correspondence-auditor CONFIRMED + chokepoint-mapper REFUTED -> REFUTED."""
    verdicts = [
        _verdict("correspondence-auditor", "CONFIRMED"),
        _verdict("chokepoint-mapper", "REFUTED"),
    ]
    assert compute_aggregate(verdicts) == "REFUTED"
    # Order must not matter.
    assert compute_aggregate(list(reversed(verdicts))) == "REFUTED"


def test_refuted_beats_untestable() -> None:
    verdicts = [_verdict("a", "UNTESTABLE"), _verdict("b", "REFUTED")]
    assert compute_aggregate(verdicts) == "REFUTED"


def test_untestable_beats_confirmed_when_no_refuted() -> None:
    verdicts = [_verdict("a", "CONFIRMED"), _verdict("b", "UNTESTABLE")]
    assert compute_aggregate(verdicts) == "UNTESTABLE"


def test_confirmed_beats_na() -> None:
    verdicts = [_verdict("a", "N/A"), _verdict("b", "CONFIRMED")]
    assert compute_aggregate(verdicts) == "CONFIRMED"


def test_na_abstention_never_lowers_all_na_stays_na() -> None:
    verdicts = [_verdict("a", "N/A"), _verdict("b", "N/A")]
    assert compute_aggregate(verdicts) == "N/A"


def test_all_confirmed_multiple_lenses() -> None:
    verdicts = [
        _verdict("a", "CONFIRMED"),
        _verdict("b", "CONFIRMED"),
        _verdict("c", "CONFIRMED"),
    ]
    assert compute_aggregate(verdicts) == "CONFIRMED"


def test_compute_coverage_counts() -> None:
    claims = [
        {
            "aggregate": "PENDING",
            "probe": None,
            "probe_eligibility": "eligible",
            "waiver": None,
        },
        {
            "aggregate": "CONFIRMED",
            "probe": {"designed": True},
            "probe_eligibility": "eligible",
            "waiver": None,
        },
        {
            "aggregate": "REFUTED",
            "probe": None,
            "probe_eligibility": "deferred",
            "waiver": {"by": "x", "reason": "y"},
        },
    ]
    coverage = compute_coverage(claims)
    assert coverage == {
        "harvested": 3,
        "verified": 2,
        "probed": 1,
        "deferred": 1,
        "waived": 1,
    }
