"""add_claims: bulk add, reusing op_add_claim's validation per element.

Covers: fresh-run creation on omitted run_id, adding into an existing run,
partial-failure isolation (one malformed element must not drop the rest of
the batch), empty/non-list rejection, and added/updated counting.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import op_add_claims, op_start_run
from amplifier_module_tool_claim_ledger.store import LedgerStore


def test_bulk_add_into_a_fresh_run_when_run_id_omitted(store: LedgerStore) -> None:
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

    assert result["ok"] is True
    assert result["run_id"].startswith("run_")
    assert result["added"] == 2
    assert result["updated"] == 0
    assert result["errors"] == []
    assert len(result["results"]) == 2
    for entry in result["results"]:
        assert entry["was_new"] is True
        assert "claim_id" in entry

    run_record = store.load(result["run_id"])
    assert run_record is not None
    assert len(run_record["claims"]) == 2


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
    result = op_add_claims(
        store,
        {
            "claims": [
                {"text": "claim 1", "type": "correspondence", "source": "src:1"},
                {"text": "claim 2", "type": "correspondence", "source": "src:2"},
                {"text": "claim 3", "type": "correspondence", "source": "src:3"},
                # claim 4: missing required 'source' -- malformed.
                {"text": "claim 4", "type": "correspondence"},
                {"text": "claim 5", "type": "correspondence", "source": "src:5"},
            ]
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
    result = op_add_claims(
        store,
        {
            "claims": [
                {"text": "claim ok", "type": "correspondence", "source": "src:1"},
                "not-a-dict",
            ]
        },
    )

    assert result["ok"] is True
    assert result["added"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["index"] == 1
    assert result["errors"][0]["error"] == "invalid_input"


def test_updated_count_reflects_idempotent_readd(store: LedgerStore) -> None:
    first = op_add_claims(
        store,
        {
            "claims": [
                {
                    "text": "returns sorted output",
                    "type": "correspondence",
                    "source": "pr-body",
                },
            ]
        },
    )
    run_id = first["run_id"]

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
