"""report: one-call gate + render_matrix, reusing both handlers verbatim.

Verifies the combined call returns exactly what calling `gate` then
`render_matrix` separately would produce, plus rejection of an unknown run_id.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_gate,
    op_render_matrix,
    op_report,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore


def _added_run(store: LedgerStore) -> str:
    result = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "returns sorted output",
            "type": "correspondence",
            "source": "pr-body",
        },
    )
    assert result["ok"] is True
    return result["run_id"]


def test_report_returns_verdict_coverage_and_matrix_in_one_call(
    store: LedgerStore,
) -> None:
    run_id = _added_run(store)

    result = op_report(store, {"run_id": run_id})

    assert result["ok"] is True
    assert result["run_id"] == run_id
    assert result["verdict"] == "INDETERMINATE"  # claim is PENDING (no verdict yet)
    assert "claim-pending" in result["indeterminate_reasons"][0]
    assert isinstance(result["blocking_claims"], list)
    assert isinstance(result["coverage"], dict)
    assert isinstance(result["matrix"], str)
    assert result["matrix"]  # non-empty markdown content


def test_report_matches_calling_gate_then_render_matrix_separately(
    store: LedgerStore,
) -> None:
    run_id = _added_run(store)

    combined = op_report(store, {"run_id": run_id, "gate_policy": "advisory"})

    gate_result = op_gate(store, {"run_id": run_id, "gate_policy": "advisory"})
    matrix_result = op_render_matrix(store, {"run_id": run_id, "format": "markdown"})

    assert combined["verdict"] == gate_result["verdict"]
    assert combined["blocking_claims"] == gate_result["blocking_claims"]
    assert combined["indeterminate_reasons"] == gate_result["indeterminate_reasons"]
    assert combined["coverage"] == gate_result["coverage"]
    assert combined["matrix"] == matrix_result["content"]


def test_report_respects_json_format(store: LedgerStore) -> None:
    run_id = _added_run(store)

    result = op_report(store, {"run_id": run_id, "format": "json"})

    assert result["ok"] is True
    matrix_result = op_render_matrix(store, {"run_id": run_id, "format": "json"})
    assert result["matrix"] == matrix_result["content"]


def test_report_rejects_unknown_run_id(store: LedgerStore) -> None:
    result = op_report(store, {"run_id": "run_does_not_exist"})

    assert result["ok"] is False
    assert result["error"] == "run_not_found"


def test_report_rejects_missing_run_id(store: LedgerStore) -> None:
    result = op_report(store, {})

    assert result["ok"] is False
    assert result["error"] == "invalid_input"
