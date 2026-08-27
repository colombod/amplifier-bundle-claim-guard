"""add_claims: bulk add, reusing op_add_claim's validation per element.

Covers: rejection (writes nothing) of an empty/missing run_id up front -- the
seam-guard symmetric with op_add_claim's own rejection -- adding into an
existing run, partial-failure isolation (one malformed element must not drop
the rest of the batch), empty/non-list rejection, and added/updated counting.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import op_add_claims, op_start_run
from amplifier_module_tool_claim_ledger.store import LedgerStore


def test_empty_run_id_on_add_claims_is_rejected_loudly_and_creates_no_run(
    store: LedgerStore,
) -> None:
    """The silent-fork seam applies to the batch op too: an empty/missing
    run_id rejects the WHOLE batch up front (no iteration, nothing written),
    symmetric with op_add_claim's own rejection."""
    result = op_add_claims(
        store,
        {
            "claims": [
                {
                    "text": "claim one",
                    "type": "correspondence",
                    "source": "docstring:a.py:1",
                },
                {
                    "text": "claim two",
                    "type": "correspondence",
                    "source": "docstring:b.py:2",
                },
            ]
        },
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_input"
    assert store.list_run_ids() == []


def test_bulk_add_into_an_existing_run(store: LedgerStore) -> None:
    started = op_start_run(store, {})
    run_id = started["run_id"]

    result = op_add_claims(
        store,
        {
            "run_id": run_id,
            "claims": [
                {
                    "text": "claim one",
                    "type": "safety",
                    "source": "docstring:c.py:3",
                },
            ],
        },
    )

    assert result["ok"] is True
    assert result["run_id"] == run_id
    assert result["added"] == 1

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["claims"]) == 1


def test_partial_failure_isolation_bad_element_does_not_drop_the_rest(
    store: LedgerStore,
) -> None:
    """One malformed claim among valid ones is isolated in `errors`; the rest
    (including claims AFTER the bad one) are still added."""
    run_id = op_start_run(store, {})["run_id"]

    result = op_add_claims(
        store,
        {
            "run_id": run_id,
            "claims": [
                {"text": "claim 1", "type": "correspondence", "source": "src:1"},
                {"text": "claim 2", "type": "correspondence", "source": "src:2"},
                {"text": "claim 3", "type": "correspondence", "source": "src:3"},
                # claim 4: missing required 'source' -- malformed.
                {"text": "claim 4", "type": "correspondence"},
                {"text": "claim 5", "type": "correspondence", "source": "src:5"},
            ],
        },
    )

    assert result["ok"] is True
    assert result["added"] == 4
    assert len(result["results"]) == 4
    assert len(result["errors"]) == 1
    assert result["errors"][0]["index"] == 3
    assert result["errors"][0]["error"] == "invalid_input"

    run_record = store.load(result["run_id"])
    assert run_record is not None
    assert len(run_record["claims"]) == 4
    texts = {c["text"] for c in run_record["claims"]}
    assert texts == {"claim 1", "claim 2", "claim 3", "claim 5"}


def test_non_dict_element_is_isolated_in_errors(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]

    result = op_add_claims(
        store,
        {
            "run_id": run_id,
            "claims": [
                {"text": "claim ok", "type": "correspondence", "source": "src:1"},
                "not-a-dict",
            ],
        },
    )

    assert result["ok"] is True
    assert result["added"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["index"] == 1
    assert result["errors"][0]["error"] == "invalid_input"


def test_updated_count_reflects_idempotent_readd(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]

    first = op_add_claims(
        store,
        {
            "run_id": run_id,
            "claims": [
                {
                    "text": "returns sorted output",
                    "type": "correspondence",
                    "source": "pr-body",
                },
            ],
        },
    )
    assert first["run_id"] == run_id

    second = op_add_claims(
        store,
        {
            "run_id": run_id,
            "claims": [
                {
                    "text": "returns sorted output",
                    "type": "correspondence",
                    "source": "pr-body",
                },
            ],
        },
    )

    assert second["ok"] is True
    assert second["added"] == 0
    assert second["updated"] == 1
    assert second["results"][0]["was_new"] is False


def test_empty_claims_list_rejected(store: LedgerStore) -> None:
    result = op_add_claims(store, {"claims": []})
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_non_list_claims_rejected(store: LedgerStore) -> None:
    result = op_add_claims(store, {"claims": "not-a-list"})
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_missing_claims_key_rejected(store: LedgerStore) -> None:
    result = op_add_claims(store, {})
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_unknown_non_empty_run_id_on_add_claims_is_rejected_not_forked(
    store: LedgerStore,
) -> None:
    """Issue #11: a non-empty run_id naming no existing run rejects the WHOLE
    batch up front (run_not_found) -- checked once, not once per element --
    and creates no run at all, symmetric with add_claim's own rejection."""
    result = op_add_claims(
        store,
        {
            "run_id": "run_never_started",
            "claims": [
                {
                    "text": "claim one",
                    "type": "correspondence",
                    "source": "docstring:a.py:1",
                },
                {
                    "text": "claim two",
                    "type": "correspondence",
                    "source": "docstring:b.py:2",
                },
            ],
        },
    )

    assert result["ok"] is False
    assert result["error"] == "run_not_found"
    assert store.list_run_ids() == []


def test_add_claims_after_start_run_is_the_sanctioned_flow(
    store: LedgerStore,
) -> None:
    """Happy path: start_run then add_claims still works exactly as before."""
    run_id = op_start_run(store, {})["run_id"]

    result = op_add_claims(
        store,
        {
            "run_id": run_id,
            "claims": [
                {
                    "text": "claim one",
                    "type": "correspondence",
                    "source": "docstring:a.py:1",
                },
            ],
        },
    )

    assert result["ok"] is True
    assert result["run_id"] == run_id
    assert result["added"] == 1
    assert result["errors"] == []
