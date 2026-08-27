"""probe_scope: gate limb 2 becomes conditional on the run's declared probe_scope.

- probe_scope == "in-scope" (default, backward-compat): unchanged -- a
  non-waived safety claim with no adverse-state test still BLOCKs with
  reason "no-adverse-state-test".
- probe_scope == "out-of-scope": such a claim contributes NO blocking reason
  and NO indeterminate reason. Instead it is surfaced as an advisory reason
  "unprobed-safety-claim:<claim_id>" on the new `advisory_reasons` list, and
  never affects the verdict.
- Waiver behavior is unchanged in BOTH modes.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_declare_roster,
    op_gate,
    op_record_verdict,
    op_report,
    op_start_run,
    op_waive,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore

_EMPTY_ROSTER = {"mandatory": [], "conditional": {}}


def _start_run(store: LedgerStore, probe_scope: str | None = None) -> dict:
    data: dict = {}
    if probe_scope is not None:
        data["probe_scope"] = probe_scope
    return op_start_run(store, data)


def _add_safety_claim(store: LedgerStore, run_id: str) -> str:
    added = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "a degraded server will not corrupt data",
            "type": "safety",
            "source": "docstring:registry.py:88",
        },
    )
    assert added["ok"] is True
    return added["claim_id"]


def _confirm(store: LedgerStore, run_id: str, claim_id: str) -> None:
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["registry.py:648"],
        },
    )
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# start_run: probe_scope field
# ---------------------------------------------------------------------------


def test_start_run_defaults_probe_scope_to_in_scope(store: LedgerStore) -> None:
    result = op_start_run(store, {})

    assert result["ok"] is True
    assert result["probe_scope"] == "in-scope"

    run_record = store.load(result["run_id"])
    assert run_record is not None
    assert run_record["probe_scope"] == "in-scope"


def test_start_run_accepts_explicit_out_of_scope(store: LedgerStore) -> None:
    result = op_start_run(store, {"probe_scope": "out-of-scope"})

    assert result["ok"] is True
    assert result["probe_scope"] == "out-of-scope"

    run_record = store.load(result["run_id"])
    assert run_record is not None
    assert run_record["probe_scope"] == "out-of-scope"


def test_start_run_rejects_invalid_probe_scope(store: LedgerStore) -> None:
    result = op_start_run(store, {"probe_scope": "sideways"})

    assert result["ok"] is False
    assert result["error"] == "invalid_input"

    # Nothing written under a fabricated run_id from this rejected call --
    # confirm the store is otherwise unaffected by a fresh start_run.
    fresh = op_start_run(store, {})
    assert fresh["ok"] is True


# ---------------------------------------------------------------------------
# in-scope / backward-compat -- limb 2 blocks exactly as before
# ---------------------------------------------------------------------------


def test_in_scope_safety_claim_without_adverse_state_test_still_blocks(
    store: LedgerStore,
) -> None:
    run_id = _start_run(store, "in-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    reasons = {
        r
        for b in result["blocking_claims"]
        if b["claim_id"] == claim_id
        for r in b["reasons"]
    }
    assert "no-adverse-state-test" in reasons
    assert result["advisory_reasons"] == []


def test_backward_compat_run_that_never_sets_probe_scope_blocks_as_before(
    store: LedgerStore,
) -> None:
    """A run that never sets probe_scope at all (start_run called with no
    field, or a run created via add_claim's auto-create path) blocks exactly
    as before -- absent probe_scope must resolve to in-scope."""
    run_id = op_start_run(store, {})["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "BLOCK"
    reasons = {
        r
        for b in result["blocking_claims"]
        if b["claim_id"] == claim_id
        for r in b["reasons"]
    }
    assert "no-adverse-state-test" in reasons
    assert result["advisory_reasons"] == []


# ---------------------------------------------------------------------------
# out-of-scope -- advisory, not blocking
# ---------------------------------------------------------------------------


def test_out_of_scope_safety_claim_without_adverse_state_test_is_advisory_not_blocking(
    store: LedgerStore,
) -> None:
    run_id = _start_run(store, "out-of-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "PASS"
    assert not any(b["claim_id"] == claim_id for b in result["blocking_claims"])
    assert f"unprobed-safety-claim:{claim_id}" in result["advisory_reasons"]
    assert not any(
        r.startswith(("claim-pending", "lens-error"))
        for r in result["indeterminate_reasons"]
    )


def test_out_of_scope_advisory_never_appears_as_indeterminate_reason(
    store: LedgerStore,
) -> None:
    run_id = _start_run(store, "out-of-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)

    result = op_gate(store, {"run_id": run_id})

    assert not any(
        f"unprobed-safety-claim:{claim_id}" == r
        for r in result["indeterminate_reasons"]
    )


def test_out_of_scope_other_blocking_limbs_still_block(store: LedgerStore) -> None:
    """probe_scope only touches limb 2 -- a REFUTED claim still BLOCKs even
    under an out-of-scope run."""
    run_id = _start_run(store, "out-of-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
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
    result = op_record_verdict(
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
    assert result["ok"] is True

    gate_result = op_gate(store, {"run_id": run_id})

    assert gate_result["verdict"] == "BLOCK"
    reasons = {
        r
        for b in gate_result["blocking_claims"]
        if b["claim_id"] == claim_id
        for r in b["reasons"]
    }
    assert "REFUTED" in reasons


# ---------------------------------------------------------------------------
# waiver clears in BOTH modes
# ---------------------------------------------------------------------------


def test_waived_safety_claim_clears_under_in_scope(store: LedgerStore) -> None:
    run_id = _start_run(store, "in-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)
    op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "accepted risk this cycle",
        },
    )

    result = op_gate(store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"})

    assert result["verdict"] == "PASS"
    assert not any(b["claim_id"] == claim_id for b in result["blocking_claims"])
    assert not any(claim_id in r for r in result["advisory_reasons"])


def test_waived_safety_claim_clears_under_out_of_scope(store: LedgerStore) -> None:
    run_id = _start_run(store, "out-of-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)
    op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "accepted risk this cycle",
        },
    )

    result = op_gate(store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"})

    assert result["verdict"] == "PASS"
    assert not any(b["claim_id"] == claim_id for b in result["blocking_claims"])
    assert not any(claim_id in r for r in result["advisory_reasons"])


# ---------------------------------------------------------------------------
# report surfaces advisory_reasons + count
# ---------------------------------------------------------------------------


def test_report_surfaces_advisory_reasons_and_count(store: LedgerStore) -> None:
    run_id = _start_run(store, "out-of-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)

    result = op_report(store, {"run_id": run_id})

    assert result["ok"] is True
    assert result["verdict"] == "PASS"
    assert f"unprobed-safety-claim:{claim_id}" in result["advisory_reasons"]
    assert result["coverage"]["advisory"] == 1
    assert "advisory" in result["matrix"].lower()


def test_report_advisory_count_is_zero_under_in_scope(store: LedgerStore) -> None:
    run_id = _start_run(store, "in-scope")["run_id"]
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    claim_id = _add_safety_claim(store, run_id)
    _confirm(store, run_id, claim_id)

    result = op_report(store, {"run_id": run_id})

    assert result["advisory_reasons"] == []
    assert result["coverage"]["advisory"] == 0


# ---------------------------------------------------------------------------
# gate result always carries advisory_reasons (possibly empty)
# ---------------------------------------------------------------------------


def test_gate_result_always_carries_advisory_reasons_key(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {"run_id": run_id, "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    op_declare_roster(store, {"run_id": run_id, **_EMPTY_ROSTER})
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": added["claim_id"],
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["x.py:1"],
        },
    )

    result = op_gate(store, {"run_id": run_id})

    assert "advisory_reasons" in result
    assert result["advisory_reasons"] == []
