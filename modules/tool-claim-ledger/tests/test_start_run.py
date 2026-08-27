"""start_run: explicit run creation -- or resume -- without adding a claim first.

Issue #10: a caller-supplied `run_id` selects resume-vs-create-at-id-vs-mint;
an invalid caller-supplied id is rejected loudly via the store's own
sanitizer/confinement check (the same one every other op already relies on).
"""

from __future__ import annotations

import pytest
from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_declare_roster,
    op_start_run,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore, WriteConfinementError


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


def test_start_run_with_omitted_run_id_still_mints(store: LedgerStore) -> None:
    """Backward-compat characterization: omitting run_id keeps minting, and
    the response says so via resumed=False."""
    result = op_start_run(store, {})

    assert result["ok"] is True
    assert result["run_id"].startswith("run_")
    assert result["resumed"] is False


def test_start_run_with_a_fresh_caller_id_creates_at_that_id(
    store: LedgerStore,
) -> None:
    """A run_id the store has never seen creates a new run AT that id (not a
    minted one), using this call's gate_policy/probe_scope."""
    result = op_start_run(
        store, {"run_id": "run_caller_chosen", "gate_policy": "advisory"}
    )

    assert result["ok"] is True
    assert result["run_id"] == "run_caller_chosen"
    assert result["gate_policy"] == "advisory"
    assert result["resumed"] is False

    run_record = store.load("run_caller_chosen")
    assert run_record is not None
    assert run_record["run_id"] == "run_caller_chosen"
    assert run_record["gate_policy"] == "advisory"
    assert run_record["claims"] == []


def test_start_run_with_an_existing_id_resumes_without_wiping_claims_or_policy(
    store: LedgerStore,
) -> None:
    """RESUME semantics: calling start_run again at an id that already has
    claims/policy/roster must return the run as-is -- never reset it -- even
    when this call passes a DIFFERENT gate_policy/probe_scope (ignored)."""
    first = op_start_run(store, {"run_id": "run_resume_me", "gate_policy": "blocking"})
    assert first["resumed"] is False

    added = op_add_claim(
        store,
        {
            "run_id": "run_resume_me",
            "text": "the drain worker is supervised",
            "type": "safety",
            "source": "docstring:worker.py:12",
        },
    )
    assert added["ok"] is True

    op_declare_roster(
        store,
        {
            "run_id": "run_resume_me",
            "mandatory": ["correspondence-auditor"],
            "conditional": {},
        },
    )

    # Resume with a DIFFERENT gate_policy/probe_scope on this call -- both
    # must be ignored; the run keeps what it already had.
    resumed = op_start_run(
        store,
        {
            "run_id": "run_resume_me",
            "gate_policy": "advisory",
            "probe_scope": "out-of-scope",
        },
    )

    assert resumed["ok"] is True
    assert resumed["run_id"] == "run_resume_me"
    assert resumed["resumed"] is True
    assert resumed["gate_policy"] == "blocking"  # unchanged, not "advisory"
    assert resumed["probe_scope"] == "in-scope"  # unchanged, not "out-of-scope"

    run_record = store.load("run_resume_me")
    assert run_record is not None
    assert run_record["gate_policy"] == "blocking"
    assert run_record["probe_scope"] == "in-scope"
    assert len(run_record["claims"]) == 1  # not wiped
    assert run_record["claims"][0]["claim_id"] == added["claim_id"]
    assert run_record["roster"] is not None  # not wiped


def test_start_run_rejects_an_invalid_caller_supplied_run_id(
    store: LedgerStore,
) -> None:
    """An invalid run_id is rejected via the SAME sanitizer/confinement check
    every other op already relies on (store.load -> ... -> sanitize_run_id) --
    raised as WriteConfinementError, exactly like any other op given a
    malformed/malicious run_id. Nothing is written."""
    with pytest.raises(WriteConfinementError):
        op_start_run(store, {"run_id": "../escape"})

    assert store.list_run_ids() == []


def test_start_run_gate_policy_validation_is_skipped_on_resume(
    store: LedgerStore,
) -> None:
    """An invalid gate_policy/probe_scope passed alongside an id that ALREADY
    resolves to an existing run must not reject the resume -- those fields
    are inert on resume, so they are never even validated on that path."""
    run_id = op_start_run(store, {"run_id": "run_resume_ignores_bad_policy"})["run_id"]

    resumed = op_start_run(
        store, {"run_id": run_id, "gate_policy": "not-a-real-policy"}
    )

    assert resumed["ok"] is True
    assert resumed["resumed"] is True
    assert resumed["gate_policy"] == "blocking-with-waiver"
