"""start_run: explicit run creation without adding a claim first."""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import op_start_run
from amplifier_module_tool_claim_ledger.store import LedgerStore


def test_start_run_creates_a_loadable_run_with_default_policy(
    store: LedgerStore,
) -> None:
    result = op_start_run(store, {})

    assert result["ok"] is True
    assert result["run_id"].startswith("run_")
    assert result["gate_policy"] == "blocking-with-waiver"

    run_record = store.load(result["run_id"])
    assert run_record is not None
    assert run_record["run_id"] == result["run_id"]
    assert run_record["gate_policy"] == "blocking-with-waiver"
    assert run_record["claims"] == []


def test_start_run_accepts_explicit_gate_policy(store: LedgerStore) -> None:
    result = op_start_run(store, {"gate_policy": "advisory"})

    assert result["ok"] is True
    assert result["gate_policy"] == "advisory"

    run_record = store.load(result["run_id"])
    assert run_record is not None
    assert run_record["gate_policy"] == "advisory"


def test_start_run_rejects_invalid_gate_policy(store: LedgerStore) -> None:
    result = op_start_run(store, {"gate_policy": "not-a-real-policy"})

    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_start_run_produces_distinct_run_ids_across_calls(store: LedgerStore) -> None:
    first = op_start_run(store, {})
    second = op_start_run(store, {})

    assert first["run_id"] != second["run_id"]
    assert store.load(first["run_id"]) is not None
    assert store.load(second["run_id"]) is not None
