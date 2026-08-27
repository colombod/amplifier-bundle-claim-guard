"""blocking_claims is grouped ONE entry per blocked claim (not per limb).

Before this change, a claim tripping N limbs produced N flat entries in
`blocking_claims` -- inflating the list an operator has to read and hiding
which entries are substantive (REFUTED) vs merely procedural
(no-adverse-state-test / UNTESTABLE-unwaived). These tests prove:

  - one entry per blocked claim, with a `reasons` list and a `category`
  - substantive entries sort before procedural entries
  - `blocking_summary` counts match
  - the VERDICT is unchanged from what the old flat-limb logic would produce
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_declare_roster,
    op_gate,
    op_record_verdict,
    op_start_run,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore

# This file exercises blocking-claim grouping/presentation and is deliberately
# indifferent to the roster-coverage limb (4c, see test_roster_coverage.py) --
# every run declares the empty-roster opt-out so the new `no-roster-declared`
# backward-compat signal never masks what this file is actually testing.
_EMPTY_ROSTER = {"mandatory": [], "conditional": {}}


def _add(
    store: LedgerStore, run_id: str, text: str, claim_type: str, source: str
) -> str:
    result = op_add_claim(
        store, {"run_id": run_id, "text": text, "type": claim_type, "source": source}
    )
    assert result["ok"] is True
    op_declare_roster(store, {"run_id": result["run_id"], **_EMPTY_ROSTER})
    return result["claim_id"]


def _confirm(store: LedgerStore, run_id: str, claim_id: str, anchor: str) -> None:
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": [anchor],
        },
    )
    assert result["ok"] is True


def _refute(
    store: LedgerStore,
    run_id: str,
    claim_id: str,
    anchor: str,
    counter_case: str,
) -> None:
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "verdict": "REFUTED",
            "evidence": [anchor],
            "counter_case": counter_case,
        },
    )
    assert result["ok"] is True


def test_claim_tripping_two_limbs_appears_exactly_once_with_scale_fixture(
    store: LedgerStore,
) -> None:
    """A >20-claim fixture proving scale/dedup: a REFUTED safety claim with no
    adverse-state test trips BOTH limb 1 and limb 2 but appears exactly once,
    with both reasons in limb order and category=substantive."""
    run_id = op_start_run(store, {})["run_id"]

    # The claim under test: REFUTED safety claim, no adverse-state test.
    double_trip_id = _add(
        store,
        run_id,
        "a degraded server will not corrupt data",
        "safety",
        "docstring:registry.py:88",
    )
    _refute(
        store,
        run_id,
        double_trip_id,
        "registry.py:648",
        "kill -9 mid-write corrupts the index",
    )

    # 24 more CONFIRMED, non-safety claims to prove this scales past the
    # "50+ blocking entries" scenario without misgrouping.
    for i in range(24):
        claim_id = _add(
            store,
            run_id,
            f"passthrough claim {i}",
            "correspondence",
            f"pr-body:{i}",
        )
        _confirm(store, run_id, claim_id, f"file{i}.py:{i + 1}")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    matches = [b for b in result["blocking_claims"] if b["claim_id"] == double_trip_id]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["reasons"] == ["REFUTED", "no-adverse-state-test"]
    assert entry["category"] == "substantive"

    # Only the one claim blocks; the 24 CONFIRMED passthroughs do not.
    assert result["blocking_summary"]["total_claims_blocked"] == 1
    assert result["blocking_summary"]["substantive"] == 1
    assert result["blocking_summary"]["procedural"] == 0


def test_safety_claim_only_no_adverse_state_test_is_procedural(
    store: LedgerStore,
) -> None:
    run_id = op_start_run(store, {})["run_id"]
    claim_id = _add(
        store,
        run_id,
        "a degraded server will not corrupt data",
        "safety",
        "docstring:registry.py:88",
    )
    _confirm(store, run_id, claim_id, "registry.py:648")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    matches = [b for b in result["blocking_claims"] if b["claim_id"] == claim_id]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["reasons"] == ["no-adverse-state-test"]
    assert entry["category"] == "procedural"


def test_untestable_unwaived_is_procedural(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]
    claim_id = _add(
        store, run_id, "concurrent writes are serialized", "concurrency", "pr-body"
    )
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "pen-tester",
            "verdict": "UNTESTABLE",
            "evidence": ["no DTU budget this run"],
        },
    )
    assert result["ok"] is True

    gate_result = op_gate(store, {"run_id": run_id})

    assert gate_result["verdict"] == "BLOCK"
    matches = [b for b in gate_result["blocking_claims"] if b["claim_id"] == claim_id]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["reasons"] == ["UNTESTABLE-unwaived"]
    assert entry["category"] == "procedural"


def test_substantive_entries_precede_procedural_entries(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]

    # Add procedural-only claim FIRST (claim order would otherwise put it
    # first in a naive per-claim-order list).
    procedural_id = _add(
        store,
        run_id,
        "a degraded server will not corrupt data",
        "safety",
        "docstring:registry.py:88",
    )
    _confirm(store, run_id, procedural_id, "registry.py:648")

    # Add substantive (REFUTED) claim SECOND.
    substantive_id = _add(
        store, run_id, "cap enforced", "quantitative", "docstring:admin.py:10"
    )
    _refute(store, run_id, substantive_id, "admin.py:972", "max_delete=0 disables cap")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    ids_in_order = [b["claim_id"] for b in result["blocking_claims"]]
    assert ids_in_order == [substantive_id, procedural_id]
    categories_in_order = [b["category"] for b in result["blocking_claims"]]
    assert categories_in_order == ["substantive", "procedural"]


def test_blocking_summary_counts_are_correct(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]

    # Two substantive (REFUTED) claims.
    refuted_1 = _add(store, run_id, "cap enforced", "quantitative", "pr-body:a")
    _refute(store, run_id, refuted_1, "a.py:1", "counter a")
    refuted_2 = _add(store, run_id, "rate limited", "quantitative", "pr-body:b")
    _refute(store, run_id, refuted_2, "b.py:2", "counter b")

    # One procedural-only (safety, no adverse-state test).
    safety_id = _add(
        store, run_id, "will not corrupt data", "safety", "docstring:c.py:3"
    )
    _confirm(store, run_id, safety_id, "c.py:3")

    # One clean CONFIRMED, non-blocking claim.
    clean_id = _add(store, run_id, "returns sorted list", "correspondence", "pr-body:d")
    _confirm(store, run_id, clean_id, "d.py:4")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    assert result["blocking_summary"] == {
        "substantive": 2,
        "procedural": 1,
        "total_claims_blocked": 3,
    }
    assert len(result["blocking_claims"]) == 3


def test_verdict_matches_old_flat_logic_across_policies(store: LedgerStore) -> None:
    """The VERDICT computation must be identical to the pre-grouping flat
    logic: BLOCK iff at least one limb tripped (non-advisory), PASS under
    advisory even with trips present."""
    run_id = op_start_run(store, {})["run_id"]
    claim_id = _add(store, run_id, "cap enforced", "quantitative", "pr-body:x")
    _refute(store, run_id, claim_id, "x.py:1", "counter x")

    blocking_result = op_gate(
        store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"}
    )
    assert blocking_result["verdict"] == "BLOCK"
    assert len(blocking_result["blocking_claims"]) == 1  # grouped, not flat-doubled

    advisory_result = op_gate(store, {"run_id": run_id, "gate_policy": "advisory"})
    assert advisory_result["verdict"] == "PASS"
    # still reported for visibility, just not blocking
    assert len(advisory_result["blocking_claims"]) == 1
