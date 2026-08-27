"""Waiving a REFUTED claim must be a LOUD, DELIBERATE act.

Closes the tool-integrity gap where `waive` on a claim whose aggregate ==
REFUTED silently cleared gate limb 1 under `blocking-with-waiver`, flipping
BLOCK -> PASS with the same one-liner used to waive an UNTESTABLE claim.

These tests exercise `op_waive` directly against the same aggregate-precedence
and gate-limb machinery `compute_aggregate`/`compute_gate` already use
elsewhere (see test_gate.py's `_refute`/`_confirm` helpers, mirrored here).
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_declare_roster,
    op_gate,
    op_record_verdict,
    op_start_run,
    op_waive,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore

# Indifferent to the roster-coverage limb (4c) -- every run declares the
# empty-roster opt-out, mirroring test_gate.py's own convention.
_EMPTY_ROSTER = {"mandatory": [], "conditional": {}}


def _add(
    store: LedgerStore, run_id: str, text: str, claim_type: str, source: str
) -> str:
    result = op_add_claim(
        store, {"run_id": run_id, "text": text, "type": claim_type, "source": source}
    )
    assert result["ok"] is True
    op_declare_roster(store, {"run_id": result["run_id"], **_EMPTY_ROSTER})
    return result["claim_id"]


def _refute(
    store: LedgerStore,
    run_id: str,
    claim_id: str,
    lens: str,
    anchor: str,
    counter_case: str,
) -> None:
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": lens,
            "verdict": "REFUTED",
            "evidence": [anchor],
            "counter_case": counter_case,
        },
    )
    assert result["ok"] is True


def test_waive_refuted_without_ack_is_refused_and_gate_stays_block(
    store: LedgerStore,
) -> None:
    """Core acceptance test: REFUTED + waive (no ack) -> refused, nothing
    written, gate stays BLOCK under the default blocking-with-waiver policy.
    """
    run_id = op_start_run(store, {})["run_id"]
    claim_id = _add(
        store, run_id, "the cache is invalidated on write", "correspondence", "pr-body"
    )
    _refute(
        store,
        run_id,
        claim_id,
        "static-verifier",
        "cache.py:42",
        "write path never calls invalidate()",
    )

    # Sanity: gate BLOCKs before any waive attempt.
    pre_gate = op_gate(store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"})
    assert pre_gate["verdict"] == "BLOCK"

    waived = op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "we'll fix it later",
        },
    )
    assert waived["ok"] is False
    assert waived["error"] == "refuted_waiver_requires_ack"
    assert claim_id in waived["message"]

    # Nothing written -- the claim's waiver field is untouched.
    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["waiver"] is None

    # Re-gate: still BLOCK. It must NOT have flipped to PASS.
    gate_result = op_gate(
        store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"}
    )
    assert gate_result["verdict"] == "BLOCK"
    reasons = {
        r
        for b in gate_result["blocking_claims"]
        if b["claim_id"] == claim_id
        for r in b["reasons"]
    }
    assert "REFUTED" in reasons


def test_waive_refuted_with_ack_clears_limb_1(store: LedgerStore) -> None:
    """Same setup, but with acknowledge_refuted=true -- waiver accepted,
    recorded with the ack flag, and gate limb 1 clears (PASS if nothing else
    blocks).
    """
    run_id = op_start_run(store, {})["run_id"]
    claim_id = _add(
        store, run_id, "the cache is invalidated on write", "correspondence", "pr-body"
    )
    _refute(
        store,
        run_id,
        claim_id,
        "static-verifier",
        "cache.py:42",
        "write path never calls invalidate()",
    )

    waived = op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "known issue, tracked separately, accepted risk",
            "acknowledge_refuted": True,
        },
    )
    assert waived["ok"] is True
    assert waived["waiver"]["acknowledge_refuted"] is True

    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    assert claim["waiver"]["acknowledge_refuted"] is True

    gate_result = op_gate(
        store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"}
    )
    assert gate_result["verdict"] == "PASS"
    assert gate_result["coverage"]["waived"] == 1


def test_waive_non_refuted_still_works_without_ack(store: LedgerStore) -> None:
    """UNTESTABLE (and, by the same code path, any other non-REFUTED
    aggregate) still waives with just by+reason -- no ack required, and the
    waiver record carries no acknowledge_refuted field.
    """
    run_id = op_start_run(store, {})["run_id"]
    claim_id = _add(
        store, run_id, "concurrent writes are serialized", "concurrency", "pr-body"
    )
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "pen-tester",
            "verdict": "UNTESTABLE",
            "evidence": ["no DTU budget this run"],
        },
    )
    assert result["ok"] is True

    waived = op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "no DTU available this cycle",
        },
    )
    assert waived["ok"] is True
    assert "acknowledge_refuted" not in waived["waiver"]

    gate_result = op_gate(
        store, {"run_id": run_id, "gate_policy": "blocking-with-waiver"}
    )
    assert gate_result["verdict"] == "PASS"


def test_waive_refuted_with_ack_never_clears_under_blocking_policy(
    store: LedgerStore,
) -> None:
    """Under `blocking`, waivers still never clear a block -- even a properly
    acknowledged REFUTED waiver.
    """
    run_id = op_start_run(store, {})["run_id"]
    claim_id = _add(
        store, run_id, "the cache is invalidated on write", "correspondence", "pr-body"
    )
    _refute(
        store,
        run_id,
        claim_id,
        "static-verifier",
        "cache.py:42",
        "write path never calls invalidate()",
    )

    waived = op_waive(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "by": "concierge",
            "reason": "accepted risk",
            "acknowledge_refuted": True,
        },
    )
    assert waived["ok"] is True

    gate_result = op_gate(store, {"run_id": run_id, "gate_policy": "blocking"})
    assert gate_result["verdict"] == "BLOCK"
