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
from .gate import compute_gate, validate_gate_policy
from .identity import compute_claim_id, identity_key, normalize_text, repo_relpath_of
from .matrix import render_json, render_markdown
from .store import LedgerStore

_VALID_VERDICTS = {"CONFIRMED", "REFUTED", "UNTESTABLE", "N/A"}
_ELIGIBLE_TYPES = {"safety", "quantitative", "temporal", "concurrency"}
_ANCHOR_RE = re.compile(r"\S+:\d+")
_PROBE_OUTCOMES = {"FALSIFIED", "SURVIVED", "UNBUILDABLE"}
_GRADUATION_MIN_DETERMINISTIC_RUNS = 3


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_run_record(run_id: str, gate_policy: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "gate_policy": gate_policy,
        "created_at": _now_iso(),
        "claims": [],
        "debate": [],
        "rejections": [],
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

    run_id = data.get("run_id") or ""
    if not run_id:
        run_id = store.new_run_id()

    run_record = store.load(run_id)
    if run_record is None:
        run_record = _new_run_record(
            run_id, data.get("gate_policy") or "blocking-with-waiver"
        )

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
    run_id = data.get("run_id")
    claim_id = data.get("claim_id")
    by = data.get("by")
    reason = data.get("reason")

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

    waiver = {"by": by, "reason": reason, "at": _now_iso()}
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
    coverage = compute_coverage(run_record["claims"])
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
    store.save(run_id, run_record)

    return compute_gate(run_record, gate_policy)


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


HANDLERS = {
    "add_claim": op_add_claim,
    "list_claims": op_list_claims,
    "record_verdict": op_record_verdict,
    "record_debate": op_record_debate,
    "waive": op_waive,
    "record_probe": op_record_probe,
    "defer_claim": op_defer_claim,
    "graduate_test": op_graduate_test,
    "aggregate": op_aggregate,
    "gate": op_gate,
    "render_matrix": op_render_matrix,
}


__all__ = [
    "HANDLERS",
    "normalize_text",
    "repo_relpath_of",
]
