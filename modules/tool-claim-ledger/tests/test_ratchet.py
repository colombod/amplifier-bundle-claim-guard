"""The evidence ratchet (structural, debate rounds): a REFUTED verdict cannot be
walked back toward CONFIRMED without at least one new file:line anchor. This is
the S-9 case: "MERGE is idempotent so it's probably fine" with no new file:line
is rejected, and the prior REFUTED stands.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import op_add_claim, op_record_verdict
from amplifier_module_tool_claim_ledger.store import LedgerStore


def _seed_refuted_claim(store: LedgerStore) -> tuple[str, str]:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "MERGE is idempotent",
            "type": "correspondence",
            "source": "docstring:merge.py:40",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]

    refuted = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "REFUTED",
            "evidence": ["merge.py:88"],
            "counter_case": "calling MERGE twice with the same key duplicates the row",
            "round": 1,
        },
    )
    assert refuted["ok"] is True
    assert refuted["aggregate"] == "REFUTED"
    return run_id, claim_id


def test_prose_alone_cannot_clear_a_refuted(store: LedgerStore) -> None:
    run_id, claim_id = _seed_refuted_claim(store)

    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["merge.py:88 -- actually this is idempotent, trust me"],
            "round": 2,
        },
    )

    assert result["ok"] is False
    assert result["error"] == "ratchet_violation"

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["aggregate"] == "REFUTED"
    assert claim["verdicts"][0]["verdict"] == "REFUTED"


def test_reciting_the_same_anchor_again_cannot_clear_a_refuted(
    store: LedgerStore,
) -> None:
    run_id, claim_id = _seed_refuted_claim(store)

    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["merge.py:88"],  # same anchor already present
            "round": 2,
        },
    )

    assert result["ok"] is False
    assert result["error"] == "ratchet_violation"


def test_a_genuinely_new_anchor_clears_the_refuted(store: LedgerStore) -> None:
    run_id, claim_id = _seed_refuted_claim(store)

    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["merge.py:104 -- upsert now guarded by a unique constraint"],
            "round": 2,
        },
    )

    assert result["ok"] is True
    assert result["verdict"] == "CONFIRMED"
    assert result["aggregate"] == "CONFIRMED"


def test_ratchet_rejection_is_appended_to_audit_trail(store: LedgerStore) -> None:
    run_id, claim_id = _seed_refuted_claim(store)

    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["merge.py:88"],
            "round": 2,
        },
    )

    run_record = store.load(run_id)
    assert run_record is not None
    ratchet_rejections = [
        r for r in run_record["rejections"] if r["error"] == "ratchet_violation"
    ]
    assert len(ratchet_rejections) == 1


def test_a_different_lens_confirming_does_not_trigger_the_ratchet_and_aggregate_stays_refuted(
    store: LedgerStore,
) -> None:
    """A fresh (not revising) CONFIRMED from a *different* lens is not a ratchet case --
    it's simply a new verdict. Worst-wins still keeps the aggregate REFUTED (S-3)."""
    run_id, claim_id = _seed_refuted_claim(store)

    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "chokepoint-mapper",
            "verdict": "CONFIRMED",
            "evidence": ["merge.py:12"],
            "round": 1,
        },
    )

    assert result["ok"] is True
    assert result["verdict"] == "CONFIRMED"
    assert result["aggregate"] == "REFUTED"
