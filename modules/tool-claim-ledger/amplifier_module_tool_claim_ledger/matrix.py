"""Render the claim-verification matrix for humans (markdown) or CI (json)."""

from __future__ import annotations

import json
from typing import Any

from .aggregate import compute_coverage
from .roster import expected_lenses


def render_json(run_record: dict[str, Any]) -> str:
    return json.dumps(run_record, indent=2)


def render_markdown(run_record: dict[str, Any]) -> str:
    roster = run_record.get("roster")
    header = (
        "| Claim | Type | Source (inferred?) | Verdict | "
        "Evidence (file:line) | Counter-case | Adverse-state test | Lens errors | "
        "Coverage gap |"
    )
    lines = [
        header,
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for claim in run_record.get("claims", []):
        lines.append(_render_row(claim, roster))

    coverage = compute_coverage(run_record.get("claims", []), roster)
    lines.append("")
    if coverage["lens_expected"] is None:
        lens_covered_cell = "n/a (no roster declared)"
    else:
        lens_covered_cell = f"{coverage['lens_covered']}/{coverage['lens_expected']}"
    # advisory count: safety claims with no adverse-state test that this run's
    # probe_scope surfaces as advisory rather than blocking (see gate.py limb 2).
    # A run that never declared probe_scope (or declared "in-scope") never
    # produces an advisory reason here -- count is always 0 in that case.
    advisory_count = _count_unprobed_safety_advisories(run_record)
    lines.append(
        f"Coverage: harvested={coverage['harvested']} verified={coverage['verified']} "
        f"lens_covered={lens_covered_cell} probed={coverage['probed']} "
        f"deferred={coverage['deferred']} waived={coverage['waived']} "
        f"advisory={advisory_count}"
    )
    return "\n".join(lines)


def _count_unprobed_safety_advisories(run_record: dict[str, Any]) -> int:
    """Mirrors gate.py limb 2's out-of-scope branch: a safety claim with no
    adverse-state test, not waived, under a run declared probe_scope ==
    "out-of-scope" is advisory rather than blocking. Zero under the default
    ("in-scope") probe_scope, matching gate's own advisory_reasons list."""
    if (run_record.get("probe_scope") or "in-scope") != "out-of-scope":
        return 0
    count = 0
    for claim in run_record.get("claims", []):
        if claim.get("type") != "safety":
            continue
        if claim.get("waiver") is not None:
            continue
        adverse_state_test = claim.get("adverse_state_test") or {}
        if not adverse_state_test.get("exists"):
            count += 1
    return count


def _render_row(claim: dict[str, Any], roster: dict[str, Any] | None) -> str:
    inferred_marker = "yes" if claim.get("inferred") else "no"
    source_cell = f"{claim.get('source', '')} ({inferred_marker})"

    evidence: list[str] = []
    counter_cases: list[str] = []
    for verdict_record in claim.get("verdicts", []):
        evidence.extend(verdict_record.get("evidence") or [])
        if verdict_record.get("counter_case"):
            counter_cases.append(verdict_record["counter_case"])

    adverse_state_test = claim.get("adverse_state_test") or {}
    adverse_state_cell = "yes" if adverse_state_test.get("exists") else "no"
    if adverse_state_test.get("test_ref"):
        adverse_state_cell += f" ({adverse_state_test['test_ref']})"

    # Lens errors are a distinct signal from a missing verdict (gate limb 4,
    # record_lens_error) -- render every recorded error so a human never has to
    # infer "lens crashed" from an otherwise-silent PENDING row.
    lens_errors_cell = (
        "; ".join(
            f"{e.get('lens', '?')}: {e.get('error', '')}"
            for e in claim.get("lens_errors") or []
        )
        or "-"
    )

    # Coverage gap: the rostered lenses that left no trace on this claim (no
    # verdict, no lens error) -- see roster.py. A gate that computes the gap
    # but does not show it here repeats the original mistake one layer up.
    covered = {v["lens"] for v in claim.get("verdicts") or []} | {
        e["lens"] for e in claim.get("lens_errors") or []
    }
    missing = [lens for lens in expected_lenses(claim, roster) if lens not in covered]
    coverage_gap_cell = ", ".join(missing) or "-"

    cells = [
        claim.get("text", ""),
        claim.get("type", ""),
        source_cell,
        claim.get("aggregate", "PENDING"),
        "; ".join(evidence) or "-",
        "; ".join(counter_cases) or "-",
        adverse_state_cell,
        lens_errors_cell,
        coverage_gap_cell,
    ]
    return "| " + " | ".join(_escape_pipe(cell) for cell in cells) + " |"


def _escape_pipe(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
