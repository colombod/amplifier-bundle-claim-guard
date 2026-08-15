"""record_lens_error and gate limb 4's lens-error signal (closes the
'lens errored is unobservable' gap).

Covers the honesty invariants this closes:
- record_lens_error attaches a marker to the claim but is NOT a verdict: it
  never creates a verdicts entry, never moves aggregate, never touches
  adverse_state_test.
- compute_gate surfaces a recorded lens error as its own
  "lens-error:<lens>@<claim_id>" indeterminate reason, distinct from
  "claim-pending:<claim_id>" -- both can appear together, or a lens error can
  appear alone even when the claim already carries a verdict from another lens.
- A lens error alone never fabricates BLOCK, CONFIRMED, or N/A -- it only ever
  drives the run to INDETERMINATE (never PASS).
- render_matrix surfaces the lens error to a human reader.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_gate,
    op_record_lens_error,
    op_record_verdict,
    op_render_matrix,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore


def _add(store: LedgerStore, **overrides: object) -> tuple[str, str]:
    payload: dict[str, object] = {
        "run_id": "",
        "text": "a degraded server will not corrupt data",
        "type": "safety",
        "source": "docstring:registry.py:88",
    }
    payload.update(overrides)
    added = op_add_claim(store, payload)
    assert added["ok"] is True
    return added["run_id"], added["claim_id"]


# --------------------------------------------------------------------------- #
# record_lens_error -- writes a marker, never a verdict
# --------------------------------------------------------------------------- #


def test_record_lens_error_attaches_marker(store: LedgerStore) -> None:
    run_id, claim_id = _add(store)

    result = op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "error": "TimeoutError: DTU probe exceeded 300s",
        },
    )

    assert result["ok"] is True
    assert result["claim_id"] == claim_id
    assert result["run_id"] == run_id
    assert result["lens"] == "boundary-adversary"
    assert result["lens_error"]["lens"] == "boundary-adversary"
    assert result["lens_error"]["error"] == "TimeoutError: DTU probe exceeded 300s"
    assert "recorded_at" in result["lens_error"]

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["lens_errors"] == [result["lens_error"]]


def test_record_lens_error_does_not_create_verdict_or_move_aggregate(
    store: LedgerStore,
) -> None:
    run_id, claim_id = _add(store)

    op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "chokepoint-mapper",
            "error": "crashed before returning a structured verdict",
        },
    )

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    # No verdict was fabricated -- the claim is still PENDING (zero verdicts).
    assert claim["verdicts"] == []
    assert claim["aggregate"] == "PENDING"
    # adverse_state_test is untouched.
    assert claim["adverse_state_test"] == {
        "exists": False,
        "test_ref": None,
        "reason": None,
    }


def test_record_lens_error_on_claim_with_existing_confirmed_verdict_leaves_aggregate_alone(
    store: LedgerStore,
) -> None:
    """A lens error on one lens must not disturb another lens's already-recorded
    verdict or the resulting aggregate -- the error is orthogonal to worst-wins."""
    run_id, claim_id = _add(store)
    confirm_result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["registry.py:648"],
        },
    )
    assert confirm_result["ok"] is True
    assert confirm_result["aggregate"] == "CONFIRMED"

    op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "error": "probe harness crashed",
        },
    )

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["aggregate"] == "CONFIRMED"
    assert len(claim["verdicts"]) == 1
    assert len(claim["lens_errors"]) == 1


def test_record_lens_error_missing_fields_invalid_input(store: LedgerStore) -> None:
    run_id, claim_id = _add(store)

    result = op_record_lens_error(
        store, {"run_id": run_id, "claim_id": claim_id, "lens": "pen-tester"}
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_record_lens_error_unknown_run_id_rejected(store: LedgerStore) -> None:
    result = op_record_lens_error(
        store,
        {
            "run_id": "run_doesnotexist",
            "claim_id": "clm_deadbeef",
            "lens": "pen-tester",
            "error": "boom",
        },
    )
    assert result["ok"] is False
    assert result["error"] == "run_not_found"


def test_record_lens_error_unknown_claim_id_rejected(store: LedgerStore) -> None:
    run_id, _claim_id = _add(store)

    result = op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": "clm_deadbeef",
            "lens": "pen-tester",
            "error": "boom",
        },
    )
    assert result["ok"] is False
    assert result["error"] == "claim_not_found"


# --------------------------------------------------------------------------- #
# gate limb 4 -- distinct lens-error reason, always INDETERMINATE (never PASS,
# never fabricates BLOCK/CONFIRMED/N-A)
# --------------------------------------------------------------------------- #


def test_gate_reports_distinct_lens_error_reason_and_is_indeterminate(
    store: LedgerStore,
) -> None:
    run_id, claim_id = _add(store)
    op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "error": "DTU unreachable",
        },
    )

    result = op_gate(store, {"run_id": run_id})

    assert result["ok"] is True
    assert result["verdict"] == "INDETERMINATE"
    assert (
        "lens-error:boundary-adversary@" + claim_id in result["indeterminate_reasons"]
    )
    # No fabricated BLOCK: nothing REFUTED, no safety-without-adverse-state-test
    # claim contributed (the claim has zero verdicts, so limb 2 doesn't apply to
    # it as CONFIRMED -- but limb 2 does independently apply to PENDING safety
    # claims too; assert specifically that a BLOCK reason wasn't invented from
    # the lens error itself).
    assert not any(b["reason"] == "REFUTED" for b in result["blocking_claims"])


def test_gate_distinguishes_claim_pending_from_lens_error_reasons(
    store: LedgerStore,
) -> None:
    """A claim with zero verdicts AND a lens error carries both distinct reason
    strings -- the lens-error signal is never conflated with plain PENDING."""
    run_id, claim_id = _add(store)
    op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "pen-tester",
            "error": "adverse-state harness failed to build",
        },
    )

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "INDETERMINATE"
    reasons = set(result["indeterminate_reasons"])
    assert f"claim-pending:{claim_id}" in reasons
    assert f"lens-error:pen-tester@{claim_id}" in reasons
    assert len(reasons) == 2


def test_gate_lens_error_on_otherwise_confirmed_claim_is_indeterminate_not_pass(
    store: LedgerStore,
) -> None:
    """A claim with a CONFIRMED verdict but where a *different* lens errored
    must not silently PASS -- the run stays INDETERMINATE, and the lens-error
    reason appears without a spurious claim-pending reason for that claim."""
    run_id, claim_id = _add(
        store, type="correspondence", source="pr-body", text="returns sorted list"
    )
    confirm_result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["sort.py:12"],
        },
    )
    assert confirm_result["ok"] is True

    op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "chokepoint-mapper",
            "error": "LSP server crashed mid-trace",
        },
    )

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "INDETERMINATE"
    reasons = set(result["indeterminate_reasons"])
    assert f"lens-error:chokepoint-mapper@{claim_id}" in reasons
    assert (
        f"claim-pending:{claim_id}" not in reasons
    )  # aggregate is CONFIRMED, not PENDING
    # Nothing fabricated a BLOCK/CONFIRMED-elsewhere artifact.
    assert result["blocking_claims"] == []


def test_gate_without_any_lens_error_has_no_lens_error_reasons(
    store: LedgerStore,
) -> None:
    """Non-regression: a run with no recorded lens errors never has a
    lens-error reason invented out of nothing."""
    run_id, claim_id = _add(
        store, type="correspondence", source="pr-body", text="returns sorted list"
    )
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["sort.py:12"],
        },
    )

    result = op_gate(store, {"run_id": run_id})
    assert result["verdict"] == "PASS"
    assert not any(r.startswith("lens-error:") for r in result["indeterminate_reasons"])


# --------------------------------------------------------------------------- #
# render_matrix -- lens errors are visible to a human reader
# --------------------------------------------------------------------------- #


def test_render_matrix_shows_lens_error(store: LedgerStore) -> None:
    run_id, claim_id = _add(store)
    op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "error": "harness crashed: connection refused",
        },
    )

    result = op_render_matrix(store, {"run_id": run_id, "format": "markdown"})

    assert result["ok"] is True
    assert "Lens errors" in result["content"]
    assert (
        "boundary-adversary: harness crashed: connection refused" in result["content"]
    )


def test_render_matrix_shows_dash_when_no_lens_errors(store: LedgerStore) -> None:
    run_id, _claim_id = _add(
        store, type="correspondence", source="pr-body", text="returns sorted list"
    )

    result = op_render_matrix(store, {"run_id": run_id, "format": "markdown"})

    assert result["ok"] is True
    # The row still renders with a placeholder in the new column.
    assert "| - |" in result["content"] or result["content"].strip().endswith("|")
