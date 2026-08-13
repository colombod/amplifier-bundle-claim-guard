"""Phase-2 probing coverage ops: record_probe, defer_claim, graduate_test.

Covers the honesty invariants this Phase-2 slice exists to guarantee:
- record_probe counts as `probed` but never itself clears gate limb 2 (a
  SURVIVED-but-ungraduated probe still blocks a safety claim).
- defer_claim counts as `deferred` but a deferred safety claim still BLOCKS
  (deferred != passed).
- graduate_test structurally rejects incomplete criteria (writes nothing) and,
  on full criteria, is the only Phase-2 path that clears limb 2.
- coverage counters (`probed`, `deferred`) reflect reality after these ops.
"""

from __future__ import annotations

import pytest
from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_defer_claim,
    op_gate,
    op_graduate_test,
    op_record_probe,
    op_record_verdict,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore

_FULL_STANDING_TEST = {
    "path": "tests/test_registry.py::test_degraded_no_corruption",
    "asserts_property": True,
    "red_before": True,
    "green_after": True,
    "deterministic_runs": 3,
}


def _add_safety_claim(store: LedgerStore) -> tuple[str, str]:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "a degraded server will not corrupt data",
            "type": "safety",
            "source": "docstring:registry.py:88",
        },
    )
    assert added["ok"] is True
    return added["run_id"], added["claim_id"]


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


# --------------------------------------------------------------------------- #
# record_probe
# --------------------------------------------------------------------------- #


def test_record_probe_sets_probe_and_counts_as_probed(store: LedgerStore) -> None:
    run_id, claim_id = _add_safety_claim(store)

    result = op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "probe": {
                "designed_by": "probe-designer",
                "adverse_state": "kill neo4j mid-write",
                "outcome": "SURVIVED",
                "evidence": ["registry.py:648"],
                "artifacts_path": ".claim-guard/probes/clm_x",
            },
        },
    )

    assert result["ok"] is True
    assert result["probe"]["outcome"] == "SURVIVED"

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["probe"] is not None
    assert claim["probe"]["outcome"] == "SURVIVED"
    assert claim["probe"]["designed_by"] == "probe-designer"


def test_record_probe_survived_does_not_clear_limb2_on_its_own(
    store: LedgerStore,
) -> None:
    """A SURVIVED probe alone must not flip adverse_state_test.exists -- only
    graduate_test can do that. A CONFIRMED safety claim with a SURVIVED-but-
    ungraduated probe still BLOCKs (B-4 shape)."""
    run_id, claim_id = _add_safety_claim(store)
    _confirm(store, run_id, claim_id)

    probe_result = op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "probe": {
                "designed_by": "pen-tester",
                "adverse_state": "kill neo4j mid-write",
                "outcome": "SURVIVED",
                "evidence": ["registry.py:648"],
                "artifacts_path": ".claim-guard/probes/clm_x",
            },
        },
    )
    assert probe_result["ok"] is True

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["adverse_state_test"]["exists"] is False

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "BLOCK"
    reasons = {
        b["reason"] for b in gate_result["blocking_claims"] if b["claim_id"] == claim_id
    }
    assert "no-adverse-state-test" in reasons
    assert gate_result["coverage"]["probed"] == 1


def test_record_probe_never_touches_verdicts_or_aggregate(store: LedgerStore) -> None:
    run_id, claim_id = _add_safety_claim(store)

    op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "probe": {
                "designed_by": "pen-tester",
                "adverse_state": "kill neo4j mid-write",
                "outcome": "FALSIFIED",
                "evidence": ["registry.py:648 -- corruption observed"],
                "artifacts_path": ".claim-guard/probes/clm_x",
            },
        },
    )

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    # record_probe writes claim.probe only -- a REFUTED verdict from the
    # FALSIFIED outcome still requires a separate record_verdict call.
    assert claim["verdicts"] == []
    assert claim["aggregate"] == "PENDING"


def test_record_probe_invalid_outcome_rejected(store: LedgerStore) -> None:
    run_id, claim_id = _add_safety_claim(store)

    result = op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "probe": {
                "designed_by": "pen-tester",
                "adverse_state": "x",
                "outcome": "MAYBE",
            },
        },
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_probe_outcome"

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["probe"] is None


def test_record_probe_missing_fields_invalid_input(store: LedgerStore) -> None:
    run_id, claim_id = _add_safety_claim(store)

    result = op_record_probe(store, {"run_id": run_id, "claim_id": claim_id})
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_record_probe_unknown_run_id(store: LedgerStore) -> None:
    result = op_record_probe(
        store,
        {
            "run_id": "run_doesnotexist",
            "claim_id": "clm_deadbeef",
            "probe": {"designed_by": "x", "adverse_state": "y", "outcome": "SURVIVED"},
        },
    )
    assert result["ok"] is False
    assert result["error"] == "run_not_found"


def test_record_probe_unknown_claim_id(store: LedgerStore) -> None:
    run_id, _claim_id = _add_safety_claim(store)

    result = op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": "clm_deadbeef",
            "probe": {"designed_by": "x", "adverse_state": "y", "outcome": "SURVIVED"},
        },
    )
    assert result["ok"] is False
    assert result["error"] == "claim_not_found"


# --------------------------------------------------------------------------- #
# defer_claim
# --------------------------------------------------------------------------- #


def test_defer_claim_sets_deferred_and_still_blocks_safety_claim(
    store: LedgerStore,
) -> None:
    run_id, claim_id = _add_safety_claim(store)
    _confirm(store, run_id, claim_id)

    result = op_defer_claim(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "reason": "no DTU budget this run",
        },
    )
    assert result["ok"] is True
    assert result["probe_eligibility"] == "deferred"

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["probe_eligibility"] == "deferred"
    # Deferring never sets adverse_state_test -- deferred != passed.
    assert claim["adverse_state_test"]["exists"] is False

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "BLOCK"
    reasons = {
        b["reason"] for b in gate_result["blocking_claims"] if b["claim_id"] == claim_id
    }
    assert "no-adverse-state-test" in reasons
    assert gate_result["coverage"]["deferred"] == 1


def test_defer_claim_not_eligible_rejected(store: LedgerStore) -> None:
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

    result = op_defer_claim(
        store, {"run_id": run_id, "claim_id": claim_id, "reason": "not applicable"}
    )
    assert result["ok"] is False
    assert result["error"] == "not_probe_eligible"

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["probe_eligibility"] == "not_eligible"


def test_defer_claim_missing_fields_invalid_input(store: LedgerStore) -> None:
    run_id, claim_id = _add_safety_claim(store)

    result = op_defer_claim(store, {"run_id": run_id, "claim_id": claim_id})
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_defer_claim_unknown_run_and_claim(store: LedgerStore) -> None:
    run_id, _claim_id = _add_safety_claim(store)

    unknown_run = op_defer_claim(
        store, {"run_id": "run_nope", "claim_id": "clm_x", "reason": "r"}
    )
    assert unknown_run["ok"] is False
    assert unknown_run["error"] == "run_not_found"

    unknown_claim = op_defer_claim(
        store, {"run_id": run_id, "claim_id": "clm_deadbeef", "reason": "r"}
    )
    assert unknown_claim["ok"] is False
    assert unknown_claim["error"] == "claim_not_found"


# --------------------------------------------------------------------------- #
# graduate_test
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "missing_field,bad_value",
    [
        ("asserts_property", False),
        ("red_before", False),
        ("green_after", False),
        ("deterministic_runs", 2),
    ],
)
def test_graduate_test_rejects_when_any_criterion_missing(
    store: LedgerStore, missing_field: str, bad_value: object
) -> None:
    run_id, claim_id = _add_safety_claim(store)
    op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "probe": {
                "designed_by": "pen-tester",
                "adverse_state": "kill neo4j mid-write",
                "outcome": "SURVIVED",
            },
        },
    )

    standing_test = dict(_FULL_STANDING_TEST)
    standing_test[missing_field] = bad_value

    result = op_graduate_test(
        store, {"run_id": run_id, "claim_id": claim_id, "standing_test": standing_test}
    )

    assert result["ok"] is False
    assert result["error"] == "graduation_criteria_unmet"

    # Nothing was written on rejection.
    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["standing_test"] is None
    assert claim["adverse_state_test"]["exists"] is False


def test_graduate_test_deterministic_runs_non_int_rejected(store: LedgerStore) -> None:
    run_id, claim_id = _add_safety_claim(store)
    standing_test = dict(_FULL_STANDING_TEST)
    standing_test["deterministic_runs"] = True  # bool is not an acceptable int count

    result = op_graduate_test(
        store, {"run_id": run_id, "claim_id": claim_id, "standing_test": standing_test}
    )
    assert result["ok"] is False
    assert result["error"] == "graduation_criteria_unmet"


def test_graduate_test_full_criteria_sets_standing_test_and_clears_limb2(
    store: LedgerStore,
) -> None:
    run_id, claim_id = _add_safety_claim(store)
    _confirm(store, run_id, claim_id)
    op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "probe": {
                "designed_by": "pen-tester",
                "adverse_state": "kill neo4j mid-write",
                "outcome": "SURVIVED",
                "evidence": ["registry.py:648"],
            },
        },
    )

    result = op_graduate_test(
        store,
        {"run_id": run_id, "claim_id": claim_id, "standing_test": _FULL_STANDING_TEST},
    )

    assert result["ok"] is True
    assert result["standing_test"]["path"] == _FULL_STANDING_TEST["path"]
    assert result["adverse_state_test"]["exists"] is True

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["standing_test"] is not None
    assert claim["standing_test"]["path"] == _FULL_STANDING_TEST["path"]
    assert claim["adverse_state_test"]["exists"] is True
    assert claim["adverse_state_test"]["test_ref"] == _FULL_STANDING_TEST["path"]

    gate_result = op_gate(store, {"run_id": run_id})
    assert gate_result["verdict"] == "PASS"


def test_graduate_test_missing_fields_invalid_input(store: LedgerStore) -> None:
    run_id, claim_id = _add_safety_claim(store)

    result = op_graduate_test(store, {"run_id": run_id, "claim_id": claim_id})
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_graduate_test_unknown_run_and_claim(store: LedgerStore) -> None:
    run_id, _claim_id = _add_safety_claim(store)

    unknown_run = op_graduate_test(
        store,
        {
            "run_id": "run_nope",
            "claim_id": "clm_x",
            "standing_test": _FULL_STANDING_TEST,
        },
    )
    assert unknown_run["ok"] is False
    assert unknown_run["error"] == "run_not_found"

    unknown_claim = op_graduate_test(
        store,
        {
            "run_id": run_id,
            "claim_id": "clm_deadbeef",
            "standing_test": _FULL_STANDING_TEST,
        },
    )
    assert unknown_claim["ok"] is False
    assert unknown_claim["error"] == "claim_not_found"


# --------------------------------------------------------------------------- #
# Coverage integration -- probed/deferred counters reflect reality
# --------------------------------------------------------------------------- #


def test_coverage_counters_reflect_probed_and_deferred_claims(
    store: LedgerStore,
) -> None:
    run_id = ""
    probed_added = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "cap enforced",
            "type": "quantitative",
            "source": "docstring:admin.py:10",
        },
    )
    run_id = probed_added["run_id"]
    probed_claim_id = probed_added["claim_id"]

    deferred_added = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "concurrent writes are serialized",
            "type": "concurrency",
            "source": "pr-body",
        },
    )
    deferred_claim_id = deferred_added["claim_id"]

    untouched_added = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "returns the sorted list",
            "type": "correspondence",
            "source": "pr-body",
        },
    )
    untouched_claim_id = untouched_added["claim_id"]

    op_record_probe(
        store,
        {
            "run_id": run_id,
            "claim_id": probed_claim_id,
            "probe": {
                "designed_by": "pen-tester",
                "adverse_state": "max_delete=0",
                "outcome": "FALSIFIED",
                "evidence": ["admin.py:972"],
            },
        },
    )
    op_defer_claim(
        store,
        {
            "run_id": run_id,
            "claim_id": deferred_claim_id,
            "reason": "no DTU budget this run",
        },
    )

    gate_result = op_gate(store, {"run_id": run_id})
    coverage = gate_result["coverage"]

    assert coverage["harvested"] == 3
    assert coverage["probed"] == 1
    assert coverage["deferred"] == 1
    # The untouched correspondence claim is neither probed nor deferred.
    run_record = store.load(run_id)
    assert run_record is not None
    untouched = next(
        c for c in run_record["claims"] if c["claim_id"] == untouched_claim_id
    )
    assert untouched["probe"] is None
    assert untouched["probe_eligibility"] == "not_eligible"
