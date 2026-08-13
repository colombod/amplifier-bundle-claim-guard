"""add_claim: idempotent re-add on stable claim_id (never resets verdicts), and
collision disambiguation for genuinely different claims sharing a computed ID.
"""

from __future__ import annotations

from unittest.mock import patch

from amplifier_module_tool_claim_ledger.ops import op_add_claim, op_record_verdict
from amplifier_module_tool_claim_ledger.store import LedgerStore


def test_first_add_claim_derives_a_run_id(store: LedgerStore) -> None:
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
    assert result["run_id"].startswith("run_")
    assert result["was_new"] is True


def test_reword_stable_readd_is_idempotent_and_preserves_verdicts(
    store: LedgerStore,
) -> None:
    first = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "A degraded server will not corrupt data.",
            "type": "safety",
            "source": "docstring:registry.py:88",
        },
    )
    run_id, claim_id = first["run_id"], first["claim_id"]

    verdict = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["registry.py:648"],
        },
    )
    assert verdict["ok"] is True

    # Re-add with trivially reworded text and a line-shifted source (same file).
    second = op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "a degraded server will not corrupt data",
            "type": "safety",
            "source": "docstring:registry.py:95",
        },
    )

    assert second["ok"] is True
    assert second["claim_id"] == claim_id
    assert second["was_new"] is False

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert len(claim["verdicts"]) == 1  # verdicts were never reset
    assert claim["aggregate"] == "CONFIRMED"
    assert claim["source"] == "docstring:registry.py:95"  # source/basis DO update


def test_probe_eligibility_derived_from_type(store: LedgerStore) -> None:
    eligible_types = ["safety", "quantitative", "temporal", "concurrency"]
    not_eligible_types = ["correspondence", "coverage"]

    for claim_type in eligible_types:
        result = op_add_claim(
            store,
            {
                "run_id": "",
                "text": f"claim for {claim_type}",
                "type": claim_type,
                "source": "pr-body",
            },
        )
        run_record = store.load(result["run_id"])
        assert run_record is not None
        claim = next(
            c for c in run_record["claims"] if c["claim_id"] == result["claim_id"]
        )
        assert claim["probe_eligibility"] == "eligible"

    for claim_type in not_eligible_types:
        result = op_add_claim(
            store,
            {
                "run_id": "",
                "text": f"claim for {claim_type}",
                "type": claim_type,
                "source": "pr-body",
            },
        )
        run_record = store.load(result["run_id"])
        assert run_record is not None
        claim = next(
            c for c in run_record["claims"] if c["claim_id"] == result["claim_id"]
        )
        assert claim["probe_eligibility"] == "not_eligible"


def test_genuine_hash_collision_gets_disambiguated_never_silently_merged(
    store: LedgerStore,
) -> None:
    """Force a collision by making compute_claim_id return the same base id for two
    genuinely different claims (different text/type/source identity triples). The
    store must never silently merge them -- it must append a -2 disambiguator."""
    added_first = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "claim one about caching",
            "type": "correspondence",
            "source": "docstring:cache.py:10",
        },
    )
    run_id = added_first["run_id"]
    first_id = added_first["claim_id"]

    with patch(
        "amplifier_module_tool_claim_ledger.ops.compute_claim_id", return_value=first_id
    ):
        added_second = op_add_claim(
            store,
            {
                "run_id": run_id,
                "text": "an entirely different claim about eviction",
                "type": "correspondence",
                "source": "docstring:eviction.py:5",
            },
        )

    assert added_second["ok"] is True
    assert added_second["was_new"] is True
    assert added_second["claim_id"] == f"{first_id}-2"
    assert added_second["claim_id"] != first_id

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["claims"]) == 2
    ids = {c["claim_id"] for c in run_record["claims"]}
    assert ids == {first_id, f"{first_id}-2"}


def test_third_genuine_collision_gets_dash_three(store: LedgerStore) -> None:
    added_first = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "claim one",
            "type": "correspondence",
            "source": "docstring:a.py:1",
        },
    )
    run_id = added_first["run_id"]
    first_id = added_first["claim_id"]

    with patch(
        "amplifier_module_tool_claim_ledger.ops.compute_claim_id", return_value=first_id
    ):
        added_second = op_add_claim(
            store,
            {
                "run_id": run_id,
                "text": "claim two",
                "type": "correspondence",
                "source": "docstring:b.py:2",
            },
        )
        added_third = op_add_claim(
            store,
            {
                "run_id": run_id,
                "text": "claim three",
                "type": "correspondence",
                "source": "docstring:c.py:3",
            },
        )

    assert added_second["claim_id"] == f"{first_id}-2"
    assert added_third["claim_id"] == f"{first_id}-3"


def test_invalid_input_missing_fields_rejected(store: LedgerStore) -> None:
    result = op_add_claim(
        store, {"run_id": "", "text": "", "type": "correspondence", "source": "pr-body"}
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_input"
