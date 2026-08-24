"""Seam probe P1 (work-tracker x claim-guard): an empty run_id used to silently
fork a claim onto a fresh run.

Adverse state: a driver has already opened a run with `start_run` (capturing run_A)
and, following the combined-flow skill, means every subsequent `add_claim` to land on
run_A. Previously, if they omitted / blanked the `run_id`, the tool did NOT fail safe --
`op_add_claim` minted a brand-new run_B and landed the claim there, silently. A later
`gate`/`report` on run_A then passed over an empty run while the driver believed their
work was verified.

`op_record_verdict` was always the safe half: an empty run_id there is rejected loudly.
The seam is now closed by making `op_add_claim` (and `op_add_claims`) symmetric with
`op_record_verdict` -- an empty/missing run_id is rejected loudly and nothing is
written, rather than silently forking a new run. `op_start_run` is the sole way to
obtain a run_id.
"""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_list_claims,
    op_record_verdict,
    op_start_run,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore

_CLAIM = {
    "text": "the drain worker is supervised",
    "type": "safety",
    "source": "docstring:worker.py:12",
}


def test_empty_run_id_on_add_claim_is_rejected_loudly(store: LedgerStore) -> None:
    """The silent-fork seam is closed: an empty run_id on add_claim is rejected
    loudly (symmetric with record_verdict) instead of minting a fresh run."""
    run_a = op_start_run(store, {})["run_id"]

    result = op_add_claim(store, {"run_id": "", **_CLAIM})

    assert result["ok"] is False
    assert result["error"] == "invalid_input"

    # No new run was forked -- run_a remains the only run that exists.
    assert store.list_run_ids() == [run_a]

    # ...and run_a, the run the driver intended and will later gate, is still empty.
    listing = op_list_claims(store, {"run_id": run_a})
    assert listing["ok"] is True
    assert listing["count"] == 0


def test_empty_run_id_on_record_verdict_is_rejected_loudly(store: LedgerStore) -> None:
    """CHARACTERIZATION: record_verdict is the safe half -- an empty run_id fails loud."""
    result = op_record_verdict(
        store,
        {
            "run_id": "",
            "claim_id": "clm_x",
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
        },
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_input"


def test_claim_meant_for_open_run_must_not_fork_on_empty_run_id(
    store: LedgerStore,
) -> None:
    """SAFE PROPERTY (achievable slice, now GREEN): a claim meant for the run the
    driver opened can never silently land on a different one -- an empty run_id
    is rejected outright, so run_a stays the only run and stays empty.

    The STRONGER property -- the claim actually landing on run_a without the
    caller repeating the run_id -- would require session/run state (routing an
    empty run_id to "the currently-open run"). That is a separate, larger item
    (wt_cg_tuning e9n: run_id <-> item_id / session binding) and is explicitly
    out of scope here; the deliverable here is strictly "reject, never silently
    fork."
    """
    run_a = op_start_run(store, {})["run_id"]

    result = op_add_claim(store, {"run_id": "", **_CLAIM})

    assert result["ok"] is False, "empty run_id must be rejected, not silently forked"
    assert result["error"] == "invalid_input"

    # No second run was created -- run_a remains the only run, and it stays empty.
    assert store.list_run_ids() == [run_a]
    listing = op_list_claims(store, {"run_id": run_a})
    assert listing["count"] == 0
