"""list_runs: read-only run enumeration that surfaces STRANDED runs.

A run is stranded when it has at least one claim and at least one of those
claims is still PENDING (no verdict recorded) -- claims were harvested but the
run was never driven through to a complete gate.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_list_runs,
    op_record_verdict,
    op_start_run,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore


def test_list_runs_on_missing_confinement_root_is_empty_not_an_error(
    store: LedgerStore,
) -> None:
    result = op_list_runs(store, {})

    assert result["ok"] is True
    assert result["runs"] == []
    assert result["count"] == 0
    assert result["stranded_count"] == 0


def test_run_with_only_pending_claims_is_stranded(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {"run_id": run_id, "text": "claim a", "type": "safety", "source": "pr-body"},
    )
    run_id = added["run_id"]

    result = op_list_runs(store, {})

    assert result["ok"] is True
    assert result["count"] == 1
    summary = result["runs"][0]
    assert summary["run_id"] == run_id
    assert summary["claims"] == 1
    assert summary["pending"] == 1
    assert summary["verified"] == 0
    assert summary["stranded"] is True
    assert summary["gate_policy"] == "blocking-with-waiver"
    assert result["stranded_count"] == 1


def test_run_with_all_claims_verdicted_is_not_stranded(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {"run_id": run_id, "text": "claim a", "type": "safety", "source": "pr-body"},
    )
    run_id = added["run_id"]

    verdict_result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": added["claim_id"],
            "lens": "safety-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["x.py:1"],
        },
    )
    assert verdict_result["ok"] is True

    result = op_list_runs(store, {})

    assert result["count"] == 1
    summary = result["runs"][0]
    assert summary["run_id"] == run_id
    assert summary["claims"] == 1
    assert summary["pending"] == 0
    assert summary["verified"] == 1
    assert summary["stranded"] is False
    assert result["stranded_count"] == 0


def test_run_with_zero_claims_is_not_stranded(store: LedgerStore) -> None:
    started = op_start_run(store, {})

    result = op_list_runs(store, {})

    assert result["count"] == 1
    summary = result["runs"][0]
    assert summary["run_id"] == started["run_id"]
    assert summary["claims"] == 0
    assert summary["pending"] == 0
    assert summary["verified"] == 0
    assert summary["stranded"] is False
    assert result["stranded_count"] == 0


def test_stranded_only_filters_but_stranded_count_reflects_true_total(
    store: LedgerStore,
) -> None:
    # Run 1: stranded (claim added, never verdicted).
    stranded_run_id = op_start_run(store, {})["run_id"]
    stranded_run = op_add_claim(
        store,
        {
            "run_id": stranded_run_id,
            "text": "stranded claim",
            "type": "safety",
            "source": "pr-body",
        },
    )

    # Run 2: fully verdicted, not stranded.
    verdicted_run_id = op_start_run(store, {})["run_id"]
    verdicted_run = op_add_claim(
        store,
        {
            "run_id": verdicted_run_id,
            "text": "verdicted claim",
            "type": "safety",
            "source": "pr-body",
        },
    )
    op_record_verdict(
        store,
        {
            "run_id": verdicted_run["run_id"],
            "claim_id": verdicted_run["claim_id"],
            "lens": "safety-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["y.py:1"],
        },
    )

    # Run 3: zero claims, not stranded.
    empty_run = op_start_run(store, {})

    full = op_list_runs(store, {})
    assert full["count"] == 3
    assert full["stranded_count"] == 1

    only_stranded = op_list_runs(store, {"stranded_only": True})
    assert only_stranded["count"] == 1
    assert only_stranded["runs"][0]["run_id"] == stranded_run["run_id"]
    # stranded_count reflects the TRUE total regardless of the filter.
    assert only_stranded["stranded_count"] == 1

    # Sanity: the non-stranded runs exist but are excluded from the filtered view.
    filtered_ids = {r["run_id"] for r in only_stranded["runs"]}
    assert verdicted_run["run_id"] not in filtered_ids
    assert empty_run["run_id"] not in filtered_ids


def test_list_runs_ordering_is_deterministic(store: LedgerStore) -> None:
    first = op_start_run(store, {})
    second = op_start_run(store, {})
    third = op_start_run(store, {})

    result_a = op_list_runs(store, {})
    result_b = op_list_runs(store, {})

    ids_a = [r["run_id"] for r in result_a["runs"]]
    ids_b = [r["run_id"] for r in result_b["runs"]]
    assert ids_a == ids_b
    assert set(ids_a) == {first["run_id"], second["run_id"], third["run_id"]}

    # Ordering matches created_at then run_id (both are already sorted keys here
    # since created_at is monotonically non-decreasing across the sequential calls).
    created_ats = [r["created_at"] for r in result_a["runs"]]
    assert created_ats == sorted(created_ats)


def test_list_runs_never_writes(store: LedgerStore) -> None:
    """Read-only: calling list_runs must not create the confinement root."""
    confinement_root = store._confinement_root()
    assert not confinement_root.exists()

    result = op_list_runs(store, {})

    assert result["ok"] is True
    assert not confinement_root.exists()
