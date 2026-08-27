"""Operation handlers for the `claim_ledger` tool.

Each `op_*` function takes `(store, data)` and returns the operation's result dict
(`{"ok": True, ...}` or `{"ok": False, "error": ..., "message": ...}`). Persistence
happens inside each handler via the `LedgerStore` passed in.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .aggregate import compute_aggregate, compute_coverage
from .gate import compute_gate, validate_gate_policy, validate_probe_scope
from .identity import compute_claim_id, identity_key, normalize_text, repo_relpath_of
from .matrix import render_json, render_markdown
from .roster import expected_lenses, validate_roster
from .store import LedgerStore

_VALID_VERDICTS = {"CONFIRMED", "REFUTED", "UNTESTABLE", "N/A"}
_ELIGIBLE_TYPES = {"safety", "quantitative", "temporal", "concurrency"}
_ANCHOR_RE = re.compile(r"\S+:\d+")
_PROBE_OUTCOMES = {"FALSIFIED", "SURVIVED", "UNBUILDABLE"}
_GRADUATION_MIN_DETERMINISTIC_RUNS = 3


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_run_record(
    run_id: str,
    gate_policy: str,
    store: LedgerStore,
    probe_scope: str = "in-scope",
) -> dict[str, Any]:
    """Create a new run record, persisting the resolved absolute ledger location.

    `ledger_root`/`ledger_path` are computed ONCE here, at run-creation time, from
    the store's own resolved confinement root -- and then persisted inside the
    record itself. This is the durability fix: the only durable artifact of a run
    (this ledger file) now carries its own absolute location, so a caller (or a
    human debugging a BLOCK verdict after the fact) never has to re-derive "where
    did this write" from a cwd that may no longer exist or may have drifted
    between calls.

    `probe_scope` ("in-scope" default | "out-of-scope") governs whether gate
    limb 2 (safety claim with no adverse-state test) BLOCKs or is merely
    surfaced as an advisory reason -- see gate.py. A run that never sets it
    (e.g. `add_claim`'s auto-create path) gets the backward-compatible default.
    """
    return {
        "run_id": run_id,
        "gate_policy": gate_policy,
        "probe_scope": probe_scope,
        "created_at": _now_iso(),
        "ledger_root": str(store.confinement_root()),
        "ledger_path": str(store.ledger_file(run_id)),
        "claims": [],
        "debate": [],
        "rejections": [],
        "gates": [],
        "roster": None,
        "roster_history": [],
    }


def _append_rejection(
    run_record: dict[str, Any],
    op: str,
    claim_id: str,
    lens: str,
    attempted_verdict: str,
    error: str,
) -> None:
    run_record.setdefault("rejections", []).append(
        {
            "op": op,
            "claim_id": claim_id,
            "lens": lens,
            "attempted_verdict": attempted_verdict,
            "error": error,
            "at": _now_iso(),
        }
    )


def _find_claim(run_record: dict[str, Any], claim_id: str) -> dict[str, Any] | None:
    return next((c for c in run_record["claims"] if c["claim_id"] == claim_id), None)


def _extract_anchors(evidence: list[str]) -> set[str]:
    anchors: set[str] = set()
    for item in evidence:
        match = _ANCHOR_RE.search(item)
        if match:
            anchors.add(match.group(0))
    return anchors


def op_add_claim(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    text = data.get("text")
    claim_type = data.get("type")
    source = data.get("source")
    if not text or not claim_type or not source:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "text, type, and source are required",
        }

    run_id = data.get("run_id")
    if not run_id:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id is required",
        }

    run_record = store.load(run_id)
    if run_record is None:
        # A non-empty but unknown run_id is a caller error, not an invitation
        # to silently fork a fresh orphan run -- symmetric with
        # op_record_verdict's run_not_found. The sanctioned flow is start_run
        # (optionally at a caller-chosen id, see op_start_run) THEN add_claim/
        # add_claims; auto-create-on-add is not supported.
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    key = identity_key(text, claim_type, source)
    base_id = compute_claim_id(text, claim_type, source)

    existing_match: dict[str, Any] | None = None
    candidate_id = base_id
    suffix_n = 1
    while True:
        found = _find_claim(run_record, candidate_id)
        if found is None:
            break
        found_key = identity_key(found["text"], found["type"], found["source"])
        if found_key == key:
            existing_match = found
            break
        suffix_n += 1
        candidate_id = f"{base_id}-{suffix_n}"

    inferred = bool(data.get("inferred", False))
    basis = data.get("basis")
    quote = data.get("quote")

    if existing_match is not None:
        existing_match["source"] = source
        existing_match["basis"] = basis
        existing_match["inferred"] = inferred
        if quote is not None:
            existing_match["quote"] = quote
        store.save(run_id, run_record)
        return {
            "ok": True,
            "claim_id": existing_match["claim_id"],
            "run_id": run_id,
            "was_new": False,
        }

    probe_eligibility = "eligible" if claim_type in _ELIGIBLE_TYPES else "not_eligible"

    claim = {
        "claim_id": candidate_id,
        "text": text,
        "type": claim_type,
        "source": source,
        "inferred": inferred,
        "basis": basis,
        "quote": quote,
        "verdicts": [],
        "aggregate": "PENDING",
        "adverse_state_test": {"exists": False, "test_ref": None, "reason": None},
        "probe_eligibility": probe_eligibility,
        "probe": None,
        "standing_test": None,
        "waiver": None,
        "lens_errors": [],
    }
    run_record["claims"].append(claim)
    store.save(run_id, run_record)
    return {"ok": True, "claim_id": candidate_id, "run_id": run_id, "was_new": True}


def op_list_claims(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    run_id = data.get("run_id")
    if not run_id:
        return {"ok": False, "error": "invalid_input", "message": "run_id is required"}
    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    claims = run_record["claims"]
    type_filter = data.get("type")
    aggregate_filter = data.get("aggregate")
    if type_filter:
        claims = [c for c in claims if c["type"] == type_filter]
    if aggregate_filter:
        claims = [c for c in claims if c["aggregate"] == aggregate_filter]
    return {"ok": True, "run_id": run_id, "claims": claims, "count": len(claims)}


def op_record_verdict(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    run_id = data.get("run_id")
    claim_id = data.get("claim_id")
    lens = data.get("lens")
    verdict = data.get("verdict")
    evidence = data.get("evidence") or []
    counter_case = data.get("counter_case")
    adverse_state_test = data.get("adverse_state_test")
    round_no = data.get("round", 1)

    if not run_id or not claim_id or not lens or not verdict:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id, claim_id, lens, and verdict are required",
        }
    if verdict not in _VALID_VERDICTS:
        return {
            "ok": False,
            "error": "invalid_verdict",
            "message": f"verdict must be one of {sorted(_VALID_VERDICTS)}, got {verdict!r}",
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    claim = _find_claim(run_record, claim_id)
    if claim is None:
        return {
            "ok": False,
            "error": "claim_not_found",
            "message": f"no claim {claim_id!r} in run {run_id!r}",
        }

    # evidence_required -- a CONFIRMED/REFUTED verdict without a file:line anchor is
    # not a verdict.
    if verdict in ("CONFIRMED", "REFUTED") and not _extract_anchors(evidence):
        _append_rejection(
            run_record, "record_verdict", claim_id, lens, verdict, "evidence_required"
        )
        store.save(run_id, run_record)
        return {
            "ok": False,
            "error": "evidence_required",
            "message": "CONFIRMED/REFUTED verdicts require at least one file:line evidence anchor",
        }

    # counter_case_required -- a refutation must name what breaks the claim.
    if verdict == "REFUTED" and not counter_case:
        _append_rejection(
            run_record,
            "record_verdict",
            claim_id,
            lens,
            verdict,
            "counter_case_required",
        )
        store.save(run_id, run_record)
        return {
            "ok": False,
            "error": "counter_case_required",
            "message": "REFUTED verdicts require a counter_case",
        }

    existing = next((v for v in claim["verdicts"] if v["lens"] == lens), None)

    # The evidence ratchet -- a lens revising its own prior REFUTED verdict toward
    # anything else must cite at least one anchor not already present anywhere in
    # this claim's existing verdict evidence. Prose alone cannot clear a REFUTED.
    if (
        existing is not None
        and existing["verdict"] == "REFUTED"
        and verdict != "REFUTED"
    ):
        prior_anchors: set[str] = set()
        for verdict_record in claim["verdicts"]:
            prior_anchors |= _extract_anchors(verdict_record.get("evidence") or [])
        new_anchors = _extract_anchors(evidence) - prior_anchors
        if not new_anchors:
            _append_rejection(
                run_record,
                "record_verdict",
                claim_id,
                lens,
                verdict,
                "ratchet_violation",
            )
            store.save(run_id, run_record)
            return {
                "ok": False,
                "error": "ratchet_violation",
                "message": (
                    "cannot move a REFUTED verdict without at least one new file:line "
                    "anchor not already present in this claim's evidence"
                ),
            }

    verdict_record = {
        "lens": lens,
        "verdict": verdict,
        "evidence": evidence,
        "counter_case": counter_case,
        "round": round_no,
        "recorded_at": _now_iso(),
    }
    if existing is not None:
        claim["verdicts"] = [
            verdict_record if v["lens"] == lens else v for v in claim["verdicts"]
        ]
    else:
        claim["verdicts"].append(verdict_record)

    if adverse_state_test is not None:
        claim["adverse_state_test"] = adverse_state_test

    claim["aggregate"] = compute_aggregate(claim["verdicts"])
    store.save(run_id, run_record)
    return {
        "ok": True,
        "claim_id": claim_id,
        "lens": lens,
        "verdict": verdict,
        "aggregate": claim["aggregate"],
    }


def op_record_lens_error(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Record that a lens errored/crashed while attempting to verify a claim.

    Makes limb 4 ("a lens errored / returned no structured verdict") fully
    observable: without this op, a crashed lens is structurally indistinguishable
    from a claim that simply hasn't been looked at yet (both read as `PENDING`).
    Appends a `{lens, error, recorded_at}` entry to `claim.lens_errors`. Never
    creates a verdict entry, never touches `claim.verdicts`/`aggregate`, and
    never touches `adverse_state_test` -- a lens error is not a verdict and must
    never be mistaken for one by `compute_aggregate` or gate limbs 1-3.
    """
    run_id = data.get("run_id")
    claim_id = data.get("claim_id")
    lens = data.get("lens")
    error = data.get("error")

    if not run_id or not claim_id or not lens or not error:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id, claim_id, lens, and error are required",
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    claim = _find_claim(run_record, claim_id)
    if claim is None:
        return {
            "ok": False,
            "error": "claim_not_found",
            "message": f"no claim {claim_id!r} in run {run_id!r}",
        }

    lens_error = {"lens": lens, "error": error, "recorded_at": _now_iso()}
    claim.setdefault("lens_errors", []).append(lens_error)
    store.save(run_id, run_record)
    return {
        "ok": True,
        "claim_id": claim_id,
        "run_id": run_id,
        "lens": lens,
        "lens_error": lens_error,
    }


def op_declare_roster(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Declare the run-level roster POLICY the gate derives per-claim expected
    lenses from (closes the silent lens-coverage hole -- see roster.py).

    Structurally rejects (writes nothing) on any validation failure from
    `validate_roster`. On success, replaces the run's `roster` wholesale,
    pushing any prior roster to `roster_history` (append-only, oldest first) so
    a mid-run re-declaration is visible rather than a silent overwrite.
    Re-declaration is a supported, expected operation, not a workaround.

    Never rejects a lens's verdict for being "off-roster" -- that is
    `record_verdict`'s job to never do (a roster typo must never discard a
    real adversarial finding); this op only ever writes the policy itself.
    """
    run_id = data.get("run_id")
    if not run_id:
        return {"ok": False, "error": "invalid_input", "message": "run_id is required"}

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    validation_error = validate_roster(data)
    if validation_error is not None:
        return {"ok": False, "error": "invalid_input", "message": validation_error}

    conditional = data.get("conditional") or {}
    new_roster = {
        "mandatory": list(data.get("mandatory") or []),
        "conditional": {
            lens: {
                "types": list(cond.get("types") or []),
                "included": cond.get("included"),
                "reason": cond.get("reason"),
            }
            for lens, cond in conditional.items()
        },
        "declared_by": data.get("declared_by"),
        "declared_at": _now_iso(),
    }

    prior_roster = run_record.get("roster")
    replaced = prior_roster is not None
    if replaced:
        run_record.setdefault("roster_history", []).append(prior_roster)
    run_record["roster"] = new_roster

    store.save(run_id, run_record)

    expected = [
        {
            "claim_id": claim["claim_id"],
            "type": claim["type"],
            "expected_lenses": expected_lenses(claim, new_roster),
        }
        for claim in run_record.get("claims", [])
    ]

    return {
        "ok": True,
        "run_id": run_id,
        "roster": new_roster,
        "expected": expected,
        "replaced": replaced,
    }


def op_record_debate(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    run_id = data.get("run_id")
    round_no = data.get("round")
    to_lens = data.get("to_lens")
    relayed_payload = data.get("relayed_payload")
    from_lenses = data.get("from_lenses") or []

    if not run_id or round_no is None or not to_lens:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id, round, and to_lens are required",
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    run_record.setdefault("debate", []).append(
        {
            "round": round_no,
            "to_lens": to_lens,
            "relayed_payload": relayed_payload,
            "from_lenses": from_lenses,
            "recorded_at": _now_iso(),
        }
    )
    store.save(run_id, run_record)
    return {"ok": True, "round": round_no, "to_lens": to_lens}


def op_waive(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Record a named human waiver on a claim.

    A REFUTED claim cannot be waived by the same one-liner as an UNTESTABLE
    one -- that would let a demonstrably FALSE claim be cleared as quietly as
    an inconclusive one, defeating the evidence ratchet at the waiver seam.
    Before writing anything, this recomputes the claim's current aggregate
    with the SAME `compute_aggregate` the gate uses (never the possibly-stale
    `claim["aggregate"]` field). If that aggregate is `REFUTED`, the caller
    must pass `acknowledge_refuted=true` -- omitting it REFUSES the waive
    (`refuted_waiver_requires_ack`) and writes NOTHING to the ledger. When the
    ack is given, the waiver is written and the acknowledgment itself is
    persisted on the waiver record (`waiver.acknowledge_refuted = true`) so a
    refuted-claim waiver is always auditable after the fact.

    For any non-REFUTED aggregate (UNTESTABLE, CONFIRMED, N/A, PENDING),
    behavior is completely unchanged -- no ack required, `by`+`reason` alone
    still waive it. `gate.py`'s `waived_clears()` is untouched: enforcement
    lives here, at the waiver-writing seam, not in the gate's read path.
    """
    run_id = data.get("run_id")
    claim_id = data.get("claim_id")
    by = data.get("by")
    reason = data.get("reason")
    acknowledge_refuted = bool(data.get("acknowledge_refuted", False))

    if not run_id or not claim_id or not by or not reason:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id, claim_id, by, and reason are required",
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    claim = _find_claim(run_record, claim_id)
    if claim is None:
        return {
            "ok": False,
            "error": "claim_not_found",
            "message": f"no claim {claim_id!r} in run {run_id!r}",
        }

    current_aggregate = compute_aggregate(claim["verdicts"])
    if current_aggregate == "REFUTED" and not acknowledge_refuted:
        return {
            "ok": False,
            "error": "refuted_waiver_requires_ack",
            "message": (
                f"claim {claim_id!r} is REFUTED; waiving a refuted claim "
                "requires acknowledge_refuted=true"
            ),
        }

    waiver = {"by": by, "reason": reason, "at": _now_iso()}
    if current_aggregate == "REFUTED":
        waiver["acknowledge_refuted"] = True
    claim["waiver"] = waiver
    store.save(run_id, run_record)
    return {"ok": True, "claim_id": claim_id, "waiver": waiver}


def op_record_probe(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Phase-2: attach a probe result to a claim.

    Writes `claim.probe` only. Never touches `verdicts`/`aggregate` (verdict changes
    still go through `record_verdict`) and never touches `adverse_state_test` --
    even a SURVIVED probe does not by itself clear gate limb 2. Only
    `graduate_test` can promote a surviving probe into a claim-clearing standing
    test.
    """
    run_id = data.get("run_id")
    claim_id = data.get("claim_id")
    probe = data.get("probe")

    if not run_id or not claim_id or not isinstance(probe, dict):
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id, claim_id, and probe (object) are required",
        }

    outcome = probe.get("outcome")
    if outcome not in _PROBE_OUTCOMES:
        return {
            "ok": False,
            "error": "invalid_probe_outcome",
            "message": (
                f"probe.outcome must be one of {sorted(_PROBE_OUTCOMES)}, "
                f"got {outcome!r}"
            ),
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    claim = _find_claim(run_record, claim_id)
    if claim is None:
        return {
            "ok": False,
            "error": "claim_not_found",
            "message": f"no claim {claim_id!r} in run {run_id!r}",
        }

    claim["probe"] = {
        "designed_by": probe.get("designed_by"),
        "adverse_state": probe.get("adverse_state"),
        "outcome": outcome,
        "evidence": probe.get("evidence") or [],
        "artifacts_path": probe.get("artifacts_path"),
        "recorded_at": _now_iso(),
    }
    store.save(run_id, run_record)
    return {"ok": True, "claim_id": claim_id, "run_id": run_id, "probe": claim["probe"]}


def op_defer_claim(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Phase-2: mark a probe-eligible claim as deferred (not probed this pass).

    Sets `probe_eligibility: "deferred"` -- the coverage `deferred` counter and
    `render_matrix` read this directly. Never touches `adverse_state_test`: a
    deferred safety claim still trips gate limb 2 (deferred != passed).
    """
    run_id = data.get("run_id")
    claim_id = data.get("claim_id")
    reason = data.get("reason")

    if not run_id or not claim_id or not reason:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id, claim_id, and reason are required",
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    claim = _find_claim(run_record, claim_id)
    if claim is None:
        return {
            "ok": False,
            "error": "claim_not_found",
            "message": f"no claim {claim_id!r} in run {run_id!r}",
        }

    if claim.get("probe_eligibility") == "not_eligible":
        return {
            "ok": False,
            "error": "not_probe_eligible",
            "message": (
                f"claim {claim_id!r} is not probe-eligible (type={claim.get('type')!r})"
            ),
        }

    claim["probe_eligibility"] = "deferred"
    claim["deferral"] = {"reason": reason, "at": _now_iso()}
    store.save(run_id, run_record)
    return {
        "ok": True,
        "claim_id": claim_id,
        "run_id": run_id,
        "probe_eligibility": "deferred",
    }


def _graduation_gaps(standing_test: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not standing_test.get("asserts_property"):
        gaps.append("asserts_property")
    if not standing_test.get("red_before"):
        gaps.append("red_before")
    if not standing_test.get("green_after"):
        gaps.append("green_after")
    runs = standing_test.get("deterministic_runs")
    if (
        not isinstance(runs, int)
        or isinstance(runs, bool)
        or runs < _GRADUATION_MIN_DETERMINISTIC_RUNS
    ):
        gaps.append(f"deterministic_runs>={_GRADUATION_MIN_DETERMINISTIC_RUNS}")
    return gaps


def op_graduate_test(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Phase-2: record that a surviving probe became a standing regression test.

    Structurally rejects (writes nothing) unless ALL of `asserts_property`,
    `red_before`, `green_after` are truthy and `deterministic_runs >= 3`. On
    success, sets `claim.standing_test` AND `claim.adverse_state_test.exists =
    true` -- this is the only path besides `record_verdict`'s
    `adverse_state_test` update that clears gate limb 2 for a claim.
    """
    run_id = data.get("run_id")
    claim_id = data.get("claim_id")
    standing_test = data.get("standing_test")

    if not run_id or not claim_id or not isinstance(standing_test, dict):
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id, claim_id, and standing_test (object) are required",
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    claim = _find_claim(run_record, claim_id)
    if claim is None:
        return {
            "ok": False,
            "error": "claim_not_found",
            "message": f"no claim {claim_id!r} in run {run_id!r}",
        }

    gaps = _graduation_gaps(standing_test)
    if gaps:
        return {
            "ok": False,
            "error": "graduation_criteria_unmet",
            "message": (
                "standing_test does not meet graduation criteria; missing: "
                + ", ".join(gaps)
            ),
        }

    recorded_standing_test = {
        "path": standing_test.get("path"),
        "asserts_property": standing_test.get("asserts_property"),
        "red_before": standing_test.get("red_before"),
        "green_after": standing_test.get("green_after"),
        "deterministic_runs": standing_test.get("deterministic_runs"),
        "recorded_at": _now_iso(),
    }
    adverse_state_test = {
        "exists": True,
        "test_ref": standing_test.get("path"),
        "reason": "graduated probe",
    }
    claim["standing_test"] = recorded_standing_test
    claim["adverse_state_test"] = adverse_state_test
    store.save(run_id, run_record)
    return {
        "ok": True,
        "claim_id": claim_id,
        "run_id": run_id,
        "standing_test": recorded_standing_test,
        "adverse_state_test": adverse_state_test,
    }


def op_aggregate(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    run_id = data.get("run_id")
    if not run_id:
        return {"ok": False, "error": "invalid_input", "message": "run_id is required"}

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    for claim in run_record["claims"]:
        claim["aggregate"] = compute_aggregate(claim["verdicts"])
    store.save(run_id, run_record)

    claims_view = [
        {
            "claim_id": c["claim_id"],
            "text": c["text"],
            "type": c["type"],
            "aggregate": c["aggregate"],
            "adverse_state_test": c["adverse_state_test"],
        }
        for c in run_record["claims"]
    ]
    coverage = compute_coverage(run_record["claims"], run_record.get("roster"))
    return {"ok": True, "run_id": run_id, "claims": claims_view, "coverage": coverage}


def op_gate(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    run_id = data.get("run_id")
    if not run_id:
        return {"ok": False, "error": "invalid_input", "message": "run_id is required"}

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    gate_policy = data.get("gate_policy") or run_record.get(
        "gate_policy", "blocking-with-waiver"
    )
    if not validate_gate_policy(gate_policy):
        return {
            "ok": False,
            "error": "invalid_gate_policy",
            "message": f"unknown gate_policy: {gate_policy!r}",
        }

    for claim in run_record["claims"]:
        claim["aggregate"] = compute_aggregate(claim["verdicts"])

    gate_result = compute_gate(run_record, gate_policy)

    run_record.setdefault("gates", []).append(
        {
            "at": _now_iso(),
            "verdict": gate_result["verdict"],
            "gate_policy": gate_policy,
            "blocking_count": len(gate_result["blocking_claims"]),
            "coverage": gate_result["coverage"],
        }
    )
    store.save(run_id, run_record)

    # Surface the durable location of this run's ledger (persisted at run-creation
    # time -- see `_new_run_record`) so a BLOCK verdict is never presented without
    # also telling the caller where its only durable record lives.
    gate_result["ledger_path"] = run_record.get("ledger_path")
    return gate_result


def op_render_matrix(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    run_id = data.get("run_id")
    fmt = data.get("format", "markdown")
    if not run_id:
        return {"ok": False, "error": "invalid_input", "message": "run_id is required"}
    if fmt not in ("markdown", "json"):
        return {
            "ok": False,
            "error": "invalid_format",
            "message": f"format must be 'markdown' or 'json', got {fmt!r}",
        }

    run_record = store.load(run_id)
    if run_record is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    for claim in run_record["claims"]:
        claim["aggregate"] = compute_aggregate(claim["verdicts"])

    content = render_json(run_record) if fmt == "json" else render_markdown(run_record)
    return {"ok": True, "content": content}


def op_start_run(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Explicitly create -- or resume -- a run, without adding a claim first.

    The sole way to obtain a run_id: `op_add_claim` and `op_add_claims` no
    longer auto-create a run on an empty/omitted `run_id` -- they reject it
    loudly instead (closing a silent-fork seam where a claim meant for an
    already-open run could land on a fresh, different one). Callers must call
    this first and pass the returned `run_id` to every subsequent op.

    An optional caller-supplied `run_id` selects among three behaviors:

    - **omitted/empty** -- mint one via `store.new_run_id()` (unchanged from
      before this was configurable).
    - **provided, and a run already exists at that id** -- RESUME it: return
      the existing `run_id`/`gate_policy`/`probe_scope`/`ledger_path` as-is.
      This never resets or overwrites the run's claims, `gate_policy`,
      `probe_scope`, or `roster` -- any `gate_policy`/`probe_scope` passed on
      *this* call are ignored, since the run already has its own. This lets a
      recipe/caller re-establish a handle on a run it (or another session)
      already opened, idempotently.
    - **provided, and no run exists at that id** -- create a new run AT that
      id (using this call's `gate_policy`/`probe_scope`), via the same
      `_new_run_record()` + `store.save()` path used for a minted id.

    A caller-supplied `run_id` is validated with the SAME sanitizer/confinement
    rules every other op already applies (`store.load()` resolves the id via
    `store.ledger_file()` -> `store.run_path()` -> `store.sanitize_run_id()`
    internally) -- an invalid id raises `WriteConfinementError`, which
    `ClaimLedgerTool.execute()` already converts to the existing
    `write_confinement_violation` error shape used for any other op given a
    malformed/malicious run_id. Nothing is written for an invalid id.

    Resolves the confinement/ledger root ONCE here (via `store`, which itself
    resolved `repo_root` once at tool-construction time -- see `ClaimLedgerTool`)
    and persists the resolved absolute `ledger_path` into the run record before
    returning it to the caller, so the caller always learns where the only
    durable record of this run lives.

    `probe_scope` ("in-scope" default | "out-of-scope") is persisted on the run
    record and read by gate limb 2 (see gate.py). Backward-compat: omitted ->
    "in-scope" -> current blocking behavior unchanged.
    """
    requested_run_id = data.get("run_id")

    if requested_run_id:
        # store.load() runs the SAME sanitizer/confinement check every other
        # op relies on (via ledger_file -> run_path -> sanitize_run_id) --
        # reused verbatim, not reimplemented. An invalid id raises
        # WriteConfinementError here, uncaught, exactly like any other op that
        # loads/saves with a bad run_id; ClaimLedgerTool.execute() is what
        # turns that into the write_confinement_violation ToolResult.
        existing_run_record = store.load(requested_run_id)
        if existing_run_record is not None:
            # RESUME -- never reset/overwrite claims, gate_policy,
            # probe_scope, or roster. This call's gate_policy/probe_scope (if
            # any) are ignored; the run keeps what it already has.
            return {
                "ok": True,
                "run_id": requested_run_id,
                "gate_policy": existing_run_record.get("gate_policy"),
                "probe_scope": existing_run_record.get("probe_scope", "in-scope"),
                "ledger_path": existing_run_record.get("ledger_path"),
                "resumed": True,
            }
        run_id = requested_run_id
    else:
        run_id = None  # minted below, after gate_policy/probe_scope validate

    gate_policy = data.get("gate_policy") or "blocking-with-waiver"
    if not validate_gate_policy(gate_policy):
        return {
            "ok": False,
            "error": "invalid_input",
            "message": f"unknown gate_policy: {gate_policy!r}",
        }

    probe_scope = data.get("probe_scope") or "in-scope"
    if not validate_probe_scope(probe_scope):
        return {
            "ok": False,
            "error": "invalid_input",
            "message": f"unknown probe_scope: {probe_scope!r}",
        }

    if run_id is None:
        run_id = store.new_run_id()

    run_record = _new_run_record(run_id, gate_policy, store, probe_scope)
    store.save(run_id, run_record)
    return {
        "ok": True,
        "run_id": run_id,
        "gate_policy": gate_policy,
        "probe_scope": probe_scope,
        "ledger_path": run_record["ledger_path"],
        "resumed": False,
    }


def op_add_claims(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Bulk-add claims, reusing `op_add_claim`'s validation for each element.

    Requires an explicit, non-empty `run_id` obtained from `start_run` --
    rejects the WHOLE batch up front (writes nothing, does not iterate) if
    `run_id` is empty/omitted (`invalid_input`) or does not name an existing
    run (`run_not_found`), symmetric with `op_add_claim`'s own rejections.
    This closes the silent-fork seam for batch adds the same way it's closed
    for single adds: no auto-created run on a missing OR unknown run_id. The
    unknown-run_id check happens once, up front, rather than once per element
    -- a systemically bad run_id would otherwise repeat the same
    `run_not_found` in every element of `errors` instead of failing the call
    the same way `op_gate`/`op_record_verdict` already do. A malformed
    *element* (bad claim shape) is still recorded in per-element `errors` and
    does NOT abort the batch -- one bad element among N valid ones must not
    drop the rest.
    """
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "claims must be a non-empty array",
        }

    run_id = data.get("run_id")
    if not run_id:
        return {
            "ok": False,
            "error": "invalid_input",
            "message": "run_id is required",
        }

    if store.load(run_id) is None:
        return {
            "ok": False,
            "error": "run_not_found",
            "message": f"no run found for run_id={run_id!r}",
        }

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    added = 0
    updated = 0

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(
                {
                    "index": index,
                    "error": "invalid_input",
                    "message": "each claim must be an object",
                }
            )
            continue

        result = op_add_claim(store, {**claim, "run_id": run_id})
        if not result["ok"]:
            errors.append(
                {
                    "index": index,
                    "error": result.get("error"),
                    "message": result.get("message"),
                }
            )
            continue

        results.append({"claim_id": result["claim_id"], "was_new": result["was_new"]})
        if result["was_new"]:
            added += 1
        else:
            updated += 1

    return {
        "ok": True,
        "run_id": run_id,
        "results": results,
        "added": added,
        "updated": updated,
        "errors": errors,
    }


def op_list_runs(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """Enumerate runs, surfacing STRANDED runs -- claims harvested but not fully gated.

    Read-only: takes no run_id, never writes, never raises on a missing/empty
    confinement root (returns `ok: True` with `runs: []`). A run is `stranded`
    when it has at least one claim and at least one of those claims is still
    `PENDING` (no verdict recorded) -- i.e. claims exist but the run was never
    driven through to a complete gate. Pass `stranded_only: true` to filter the
    returned list to just those runs; `stranded_count` always reflects the true
    total across ALL runs regardless of the filter.
    """
    stranded_only = bool(data.get("stranded_only", False))

    summaries: list[dict[str, Any]] = []
    for run_id in store.list_run_ids():
        run_record = store.load(run_id)
        if run_record is None:
            continue

        claims = run_record.get("claims", [])
        total_claims = len(claims)
        pending = sum(1 for c in claims if c.get("aggregate") == "PENDING")
        verified = total_claims - pending
        stranded = total_claims > 0 and pending > 0
        gates = run_record.get("gates") or []

        summaries.append(
            {
                "run_id": run_id,
                "created_at": run_record.get("created_at"),
                "claims": total_claims,
                "pending": pending,
                "verified": verified,
                "stranded": stranded,
                "gate_policy": run_record.get("gate_policy"),
                "gated": len(gates) > 0,
                "gate_count": len(gates),
                "last_verdict": gates[-1]["verdict"] if gates else None,
                "last_gate_at": gates[-1]["at"] if gates else None,
            }
        )

    stranded_count = sum(1 for s in summaries if s["stranded"])

    if stranded_only:
        summaries = [s for s in summaries if s["stranded"]]

    summaries.sort(key=lambda s: (s.get("created_at") or "", s["run_id"]))

    return {
        "ok": True,
        "runs": summaries,
        "count": len(summaries),
        "stranded_count": stranded_count,
    }


def op_report(store: LedgerStore, data: dict[str, Any]) -> dict[str, Any]:
    """One-call gate verdict + rendered matrix.

    Thin composition of `op_gate` + `op_render_matrix` -- reuses both handlers'
    validation (missing/unknown run_id, invalid gate_policy, invalid format)
    verbatim rather than reimplementing any of it. Equivalent to calling `gate`
    then `render_matrix` separately, in one round trip.
    """
    run_id = data.get("run_id")
    gate_policy = data.get("gate_policy")
    fmt = data.get("format", "markdown")

    gate_data: dict[str, Any] = {"run_id": run_id}
    if gate_policy is not None:
        gate_data["gate_policy"] = gate_policy
    gate_result = op_gate(store, gate_data)
    if not gate_result["ok"]:
        return gate_result

    matrix_result = op_render_matrix(store, {"run_id": run_id, "format": fmt})
    if not matrix_result["ok"]:
        return matrix_result

    return {
        "ok": True,
        "run_id": run_id,
        "verdict": gate_result["verdict"],
        "blocking_claims": gate_result["blocking_claims"],
        "blocking_summary": gate_result["blocking_summary"],
        "indeterminate_reasons": gate_result["indeterminate_reasons"],
        "advisory_reasons": gate_result["advisory_reasons"],
        "coverage": gate_result["coverage"],
        "ledger_path": gate_result.get("ledger_path"),
        "matrix": matrix_result["content"],
    }


HANDLERS = {
    "add_claim": op_add_claim,
    "list_claims": op_list_claims,
    "record_verdict": op_record_verdict,
    "record_lens_error": op_record_lens_error,
    "declare_roster": op_declare_roster,
    "record_debate": op_record_debate,
    "waive": op_waive,
    "record_probe": op_record_probe,
    "defer_claim": op_defer_claim,
    "graduate_test": op_graduate_test,
    "aggregate": op_aggregate,
    "gate": op_gate,
    "render_matrix": op_render_matrix,
    "start_run": op_start_run,
    "add_claims": op_add_claims,
    "report": op_report,
    "list_runs": op_list_runs,
}


__all__ = [
    "HANDLERS",
    "normalize_text",
    "repo_relpath_of",
]
