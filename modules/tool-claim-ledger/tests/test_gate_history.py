"""Gate-invocation persistence: was this run gated, with what verdict, and when.

`op_gate` now appends a `{at, verdict, gate_policy, blocking_count, coverage}`
invocation record to `run_record["gates"]` and persists it -- so gate history
is answerable from ledger.json alone, without recomputing anything. Covers:
fresh run has no gate history, repeated `gate` calls grow an ordered history,
`report` records exactly one invocation (not zero, not two), and `list_runs`
surfaces the derived `gated`/`gate_count`/`last_verdict`/`last_gate_at` fields.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_gate,
    op_list_runs,
    op_record_verdict,
    op_report,
    op_start_run,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore


def _confirmed_run(store: LedgerStore) -> tuple[str, str]:
    """A run with a single CONFIRMED (non-safety) claim -- gates PASS."""
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "returns sorted output",
            "type": "correspondence",
            "source": "pr-body",
        },
    )
    claim_id = added["claim_id"]
    verdict_result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["sort.py:12"],
        },
    )
    assert verdict_result["ok"] is True
    return run_id, claim_id


def _refuted_run(store: LedgerStore) -> tuple[str, str]:
    """A run with a single REFUTED claim -- gates BLOCK."""
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "cap enforced",
            "type": "quantitative",
            "source": "docstring:admin.py:10",
        },
    )
    claim_id = added["claim_id"]
    verdict_result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "verdict": "REFUTED",
            "evidence": ["admin.py:972"],
            "counter_case": "max_delete=0 disables the cap",
        },
    )
    assert verdict_result["ok"] is True
    return run_id, claim_id


def test_fresh_run_has_no_gate_history(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]

    run_record = store.load(run_id)
    assert run_record is not None
    assert run_record["gates"] == []

    result = op_list_runs(store, {})
    summary = next(r for r in result["runs"] if r["run_id"] == run_id)
    assert summary["gated"] is False
    assert summary["gate_count"] == 0
    assert summary["last_verdict"] is None
    assert summary["last_gate_at"] is None


def test_gate_appends_one_invocation_with_verdict_and_timestamp(
    store: LedgerStore,
) -> None:
    run_id, _claim_id = _confirmed_run(store)

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "PASS"

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["gates"]) == 1
    invocation = run_record["gates"][0]
    assert invocation["verdict"] == "PASS"
    assert invocation["gate_policy"] == "blocking-with-waiver"
    assert invocation["blocking_count"] == 0
    assert isinstance(invocation["coverage"], dict)
    assert invocation["at"]


def test_repeated_gate_calls_grow_ordered_history(store: LedgerStore) -> None:
    run_id, _claim_id = _confirmed_run(store)

    first = op_gate(store, {"run_id": run_id})
    second = op_gate(store, {"run_id": run_id})
    assert first["verdict"] == "PASS"
    assert second["verdict"] == "PASS"

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["gates"]) == 2
    at_values = [g["at"] for g in run_record["gates"]]
    assert at_values == sorted(at_values)


def test_report_records_exactly_one_invocation(store: LedgerStore) -> None:
    run_id, _claim_id = _confirmed_run(store)

    result = op_report(store, {"run_id": run_id})
    assert result["ok"] is True

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["gates"]) == 1
    assert run_record["gates"][0]["verdict"] == result["verdict"]


def test_list_runs_surfaces_gate_history_for_gated_run(store: LedgerStore) -> None:
    run_id, _claim_id = _confirmed_run(store)
    gate_result = op_gate(store, {"run_id": run_id})

    result = op_list_runs(store, {})
    summary = next(r for r in result["runs"] if r["run_id"] == run_id)

    assert summary["gated"] is True
    assert summary["gate_count"] == 1
    assert summary["last_verdict"] == gate_result["verdict"]
    run_record = store.load(run_id)
    assert run_record is not None
    assert summary["last_gate_at"] == run_record["gates"][-1]["at"]


def test_list_runs_reflects_last_of_multiple_invocations(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "cap enforced",
            "type": "quantitative",
            "source": "docstring:admin.py:10",
        },
    )
    claim_id = added["claim_id"]

    # First gate: still PENDING -> INDETERMINATE.
    first = op_gate(store, {"run_id": run_id})
    assert first["verdict"] == "INDETERMINATE"

    # Confirm the claim, gate again -> PASS.
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["admin.py:10"],
        },
    )
    second = op_gate(store, {"run_id": run_id})
    assert second["verdict"] == "PASS"

    result = op_list_runs(store, {})
    summary = next(r for r in result["runs"] if r["run_id"] == run_id)
    assert summary["gate_count"] == 2
    assert summary["last_verdict"] == "PASS"


def test_persisted_verdict_matches_returned_verdict_for_pass_run(
    store: LedgerStore,
) -> None:
    run_id, _claim_id = _confirmed_run(store)

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "PASS"

    run_record = store.load(run_id)
    assert run_record is not None
    assert run_record["gates"][-1]["verdict"] == "PASS"


def test_persisted_verdict_matches_returned_verdict_for_block_run(
    store: LedgerStore,
) -> None:
    run_id, _claim_id = _refuted_run(store)

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "BLOCK"

    run_record = store.load(run_id)
    assert run_record is not None
    assert run_record["gates"][-1]["verdict"] == "BLOCK"


def test_gate_history_survives_missing_gates_key_backward_compat(
    store: LedgerStore,
) -> None:
    """A run record persisted before this feature existed has no "gates" key.

    `op_gate` must treat that as an empty history rather than raising.
    """
    run_id, _claim_id = _confirmed_run(store)

    run_record = store.load(run_id)
    assert run_record is not None
    del run_record["gates"]
    store.save(run_id, run_record)

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "PASS"

    updated = store.load(run_id)
    assert updated is not None
    assert len(updated["gates"]) == 1
    assert updated["gates"][0]["verdict"] == "PASS"
