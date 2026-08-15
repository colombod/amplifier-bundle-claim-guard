"""file:line evidence enforcement (structural): CONFIRMED/REFUTED without an anchor
rejected; REFUTED without a counter-case rejected. Nothing is written on rejection.
"""

from __future__ import annotations

import pytest

from amplifier_module_tool_claim_ledger.ops import op_add_claim, op_record_verdict
from amplifier_module_tool_claim_ledger.store import LedgerStore


def _seed_claim(store: LedgerStore) -> tuple[str, str]:
    result = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "a degraded server will not corrupt data",
            "type": "safety",
            "source": "docstring:registry.py:88",
            "inferred": True,
            "basis": "purpose-inquisitor derivation",
        },
    )
    assert result["ok"] is True
    return result["run_id"], result["claim_id"]


@pytest.mark.parametrize("verdict", ["CONFIRMED", "REFUTED"])
def test_confirmed_or_refuted_without_anchor_is_rejected(
    store: LedgerStore, verdict: str
) -> None:
    run_id, claim_id = _seed_claim(store)

    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": verdict,
            "evidence": ["no anchor here, just prose"],
            "counter_case": "some input" if verdict == "REFUTED" else None,
        },
    )

    assert result["ok"] is False
    assert result["error"] == "evidence_required"

    # Nothing was written: the claim still has zero verdicts.
    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["verdicts"] == []
    assert claim["aggregate"] == "PENDING"


def test_confirmed_with_anchor_is_accepted(store: LedgerStore) -> None:
    run_id, claim_id = _seed_claim(store)

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
    assert result["aggregate"] == "CONFIRMED"


def test_refuted_without_counter_case_is_rejected(store: LedgerStore) -> None:
    run_id, claim_id = _seed_claim(store)

    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "chokepoint-mapper",
            "verdict": "REFUTED",
            "evidence": ["admin.py:972"],
            "counter_case": "",
        },
    )

    assert result["ok"] is False
    assert result["error"] == "counter_case_required"

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["verdicts"] == []


def test_refuted_with_anchor_and_counter_case_is_accepted(store: LedgerStore) -> None:
    run_id, claim_id = _seed_claim(store)

    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "chokepoint-mapper",
            "verdict": "REFUTED",
            "evidence": ["admin.py:972 -- no Field(ge=1)"],
            "counter_case": "max_delete=0 bypasses the safety cap entirely",
        },
    )

    assert result["ok"] is True
    assert result["verdict"] == "REFUTED"
    assert result["aggregate"] == "REFUTED"


def test_untestable_and_na_do_not_require_an_anchor(store: LedgerStore) -> None:
    run_id, claim_id = _seed_claim(store)

    untestable = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "pen-tester",
            "verdict": "UNTESTABLE",
            "evidence": ["no DTU budget available this run"],
        },
    )
    assert untestable["ok"] is True

    na = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "verdict": "N/A",
            "evidence": ["not a boundary-shaped claim"],
        },
    )
    assert na["ok"] is True


def test_rejections_are_appended_to_audit_trail(store: LedgerStore) -> None:
    run_id, claim_id = _seed_claim(store)

    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": [],
        },
    )

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["rejections"]) == 1
    assert run_record["rejections"][0]["error"] == "evidence_required"
    assert run_record["rejections"][0]["claim_id"] == claim_id
