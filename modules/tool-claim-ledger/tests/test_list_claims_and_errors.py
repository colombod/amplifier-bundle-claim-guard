"""list_claims filters and not-found error paths across operations."""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_list_claims,
    op_record_verdict,
    op_waive,
)


def test_list_claims_filters_by_type_and_aggregate(store) -> None:
    a = op_add_claim(
        store, {"run_id": "", "text": "claim a", "type": "safety", "source": "pr-body"}
    )
    run_id = a["run_id"]
    b = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "claim b",
            "type": "correspondence",
            "source": "pr-body",
        },
    )

    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": b["claim_id"],
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["x.py:1"],
        },
    )

    only_safety = op_list_claims(store, {"run_id": run_id, "type": "safety"})
    assert only_safety["count"] == 1
    assert only_safety["claims"][0]["claim_id"] == a["claim_id"]

    only_confirmed = op_list_claims(store, {"run_id": run_id, "aggregate": "CONFIRMED"})
    assert only_confirmed["count"] == 1
    assert only_confirmed["claims"][0]["claim_id"] == b["claim_id"]


def test_list_claims_unknown_run_id(store) -> None:
    result = op_list_claims(store, {"run_id": "run_nope"})
    assert result["ok"] is False
    assert result["error"] == "run_not_found"


def test_record_verdict_unknown_claim_id(store) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    result = op_record_verdict(
        store,
        {
            "run_id": added["run_id"],
            "claim_id": "clm_deadbeef",
            "lens": "l",
            "verdict": "CONFIRMED",
            "evidence": ["a.py:1"],
        },
    )
    assert result["ok"] is False
    assert result["error"] == "claim_not_found"


def test_record_verdict_invalid_verdict_value(store) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    result = op_record_verdict(
        store,
        {
            "run_id": added["run_id"],
            "claim_id": added["claim_id"],
            "lens": "l",
            "verdict": "MAYBE",
            "evidence": ["a.py:1"],
        },
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_verdict"


def test_waive_unknown_claim(store) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    result = op_waive(
        store,
        {
            "run_id": added["run_id"],
            "claim_id": "clm_deadbeef",
            "by": "me",
            "reason": "r",
        },
    )
    assert result["ok"] is False
    assert result["error"] == "claim_not_found"
