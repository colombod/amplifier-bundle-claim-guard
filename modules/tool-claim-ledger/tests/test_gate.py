"""Gate limbs: each of the five independently, plus limb-2-with-CONFIRMED (B-4),
plus the three policy modifiers, plus zero-claims->INDETERMINATE (S-8).
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_gate,
    op_record_verdict,
    op_waive,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore


def _add(
    store: LedgerStore, run_id: str, text: str, claim_type: str, source: str
) -> str:
    result = op_add_claim(
        store, {"run_id": run_id, "text": text, "type": claim_type, "source": source}
    )
    assert result["ok"] is True
    return result["claim_id"]


def _confirm(
    store: LedgerStore, run_id: str, claim_id: str, lens: str, anchor: str
) -> None:
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": lens,
            "verdict": "CONFIRMED",
            "evidence": [anchor],
        },
    )
    assert result["ok"] is True


def _refute(
    store: LedgerStore,
    run_id: str,
    claim_id: str,
    lens: str,
    anchor: str,
    counter_case: str,
) -> None:
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": lens,
            "verdict": "REFUTED",
            "evidence": [anchor],
            "counter_case": counter_case,
        },
    )
    assert result["ok"] is True


def test_zero_claims_is_indeterminate_s8(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    run_id = added["run_id"]
    # Remove the claim to simulate a harvest that produced nothing, keeping the run.
    run_record = store.load(run_id)
    assert run_record is not None
    run_record["claims"] = []
    store.save(run_id, run_record)

    result = op_gate(store, {"run_id": run_id})

    assert result["ok"] is True
    assert result["verdict"] == "INDETERMINATE"
    assert "zero-claims-harvested" in result["indeterminate_reasons"]


def test_pending_claim_is_indeterminate(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "unverdicted claim",
            "type": "correspondence",
            "source": "pr-body",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "INDETERMINATE"
    assert any(
        reason.startswith(f"claim-pending:{claim_id}")
        for reason in result["indeterminate_reasons"]
    )


def test_limb1_any_refuted_blocks(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "cap enforced",
            "type": "quantitative",
            "source": "docstring:admin.py:10",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    _refute(
        store,
        run_id,
        claim_id,
        "boundary-adversary",
        "admin.py:972",
        "max_delete=0 disables the cap",
    )

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    reasons = {
        b["reason"] for b in result["blocking_claims"] if b["claim_id"] == claim_id
    }
    assert "REFUTED" in reasons


def test_limb2_confirmed_safety_claim_without_adverse_state_test_still_blocks_b4(
    store: LedgerStore,
) -> None:
    """The B-4 case: tests certified the wrong thing. A CONFIRMED safety claim with no
    adverse-state test still BLOCKs, independent of limb 1."""
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "a degraded server will not corrupt data",
            "type": "safety",
            "source": "docstring:registry.py:88",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    _confirm(store, run_id, claim_id, "correspondence-auditor", "registry.py:648")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    reasons = {
        b["reason"] for b in result["blocking_claims"] if b["claim_id"] == claim_id
    }
    assert "no-adverse-state-test" in reasons


def test_limb2_clears_when_adverse_state_test_exists(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "a degraded server will not corrupt data",
            "type": "safety",
            "source": "docstring:registry.py:88",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["registry.py:648"],
            "adverse_state_test": {
                "exists": True,
                "test_ref": "test_registry.py::test_degraded_no_corruption",
                "reason": "graduated probe",
            },
        },
    )
    assert result["ok"] is True

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "PASS"


def test_limb3_untestable_blocks_under_blocking_with_waiver_by_default(
    store: LedgerStore,
) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "concurrent writes are serialized",
            "type": "concurrency",
            "source": "pr-body",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
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

    gate_result = op_gate(
        store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"}
    )
    assert gate_result["verdict"] == "BLOCK"
    reasons = {
        b["reason"] for b in gate_result["blocking_claims"] if b["claim_id"] == claim_id
    }
    assert "UNTESTABLE-unwaived" in reasons


def test_limb3_waiver_clears_under_blocking_with_waiver(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "concurrent writes are serialized",
            "type": "concurrency",
            "source": "pr-body",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "pen-tester",
            "verdict": "UNTESTABLE",
            "evidence": ["no DTU budget this run"],
        },
    )
    waived = op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "no DTU available this cycle",
        },
    )
    assert waived["ok"] is True

    gate_result = op_gate(
        store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"}
    )
    assert gate_result["verdict"] == "PASS"
    assert gate_result["coverage"]["waived"] == 1


def test_waiver_does_not_clear_under_blocking_policy(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "concurrent writes are serialized",
            "type": "concurrency",
            "source": "pr-body",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "pen-tester",
            "verdict": "UNTESTABLE",
            "evidence": ["no DTU budget this run"],
        },
    )
    op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "no DTU available",
        },
    )

    gate_result = op_gate(store, {"run_id": run_id, "gate_policy": "blocking"})
    assert gate_result["verdict"] == "BLOCK"


def test_untestable_is_reported_not_blocked_under_advisory(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "concurrent writes are serialized",
            "type": "concurrency",
            "source": "pr-body",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "pen-tester",
            "verdict": "UNTESTABLE",
            "evidence": ["no DTU budget this run"],
        },
    )

    gate_result = op_gate(store, {"run_id": run_id, "gate_policy": "advisory"})
    assert gate_result["verdict"] == "PASS"
    reasons = {
        b["reason"] for b in gate_result["blocking_claims"] if b["claim_id"] == claim_id
    }
    assert "UNTESTABLE-unwaived" in reasons  # still reported


def test_advisory_never_blocks_even_with_refuted_claim(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "cap enforced",
            "type": "quantitative",
            "source": "docstring:admin.py:10",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    _refute(
        store,
        run_id,
        claim_id,
        "boundary-adversary",
        "admin.py:972",
        "max_delete=0 disables the cap",
    )

    gate_result = op_gate(store, {"run_id": run_id, "gate_policy": "advisory"})
    assert gate_result["verdict"] == "PASS"
    assert any(b["reason"] == "REFUTED" for b in gate_result["blocking_claims"])


def test_all_confirmed_no_safety_no_untestable_passes(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "returns the sorted list",
            "type": "correspondence",
            "source": "pr-body",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    _confirm(store, run_id, claim_id, "correspondence-auditor", "sort.py:12")

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "PASS"
    assert gate_result["blocking_claims"] == []
    assert gate_result["indeterminate_reasons"] == []


def test_invalid_gate_policy_is_rejected(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    run_id = added["run_id"]

    result = op_gate(store, {"run_id": run_id, "gate_policy": "made-up-policy"})
    assert result["ok"] is False
    assert result["error"] == "invalid_gate_policy"
