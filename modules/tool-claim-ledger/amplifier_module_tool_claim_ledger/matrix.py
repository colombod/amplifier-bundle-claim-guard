"""Render the claim-verification matrix for humans (markdown) or CI (json)."""

from __future__ import annotations

import json
from typing import Any

from .aggregate import compute_coverage


def render_json(run_record: dict[str, Any]) -> str:
    return json.dumps(run_record, indent=2)


def render_markdown(run_record: dict[str, Any]) -> str:
    header = (
        "| Claim | Type | Source (inferred?) | Load-bearing code | Verdict | "
        "Evidence (file:line) | Counter-case | Adverse-state test |"
    )
    lines = [
        header,
        "|---|---|---|---|---|---|---|---|",
    ]
    for claim in run_record.get("claims", []):
        lines.append(_render_row(claim))

    coverage = compute_coverage(run_record.get("claims", []))
    lines.append("")
    lines.append(
        f"Coverage: harvested={coverage['harvested']} verified={coverage['verified']} "
        f"probed={coverage['probed']} deferred={coverage['deferred']} waived={coverage['waived']}"
    )
    return "\n".join(lines)


def _render_row(claim: dict[str, Any]) -> str:
    inferred_marker = "yes" if claim.get("inferred") else "no"
    source_cell = f"{claim.get('source', '')} ({inferred_marker})"

    evidence: list[str] = []
    counter_cases: list[str] = []
    for verdict_record in claim.get("verdicts", []):
        evidence.extend(verdict_record.get("evidence") or [])
        if verdict_record.get("counter_case"):
            counter_cases.append(verdict_record["counter_case"])

    # NOTE: "Load-bearing code" has no dedicated field in the MVP schema (see
    # docs/tool-claim-ledger-contract.md data model). It renders from the same
    # file:line evidence chokepoint-mapper/boundary-adversary record, duplicating
    # the Evidence column, since no separate field carries this distinctly.
    load_bearing_cell = "; ".join(evidence) or "-"

    adverse_state_test = claim.get("adverse_state_test") or {}
    adverse_state_cell = "yes" if adverse_state_test.get("exists") else "no"
    if adverse_state_test.get("test_ref"):
        adverse_state_cell += f" ({adverse_state_test['test_ref']})"

    cells = [
        claim.get("text", ""),
        claim.get("type", ""),
        source_cell,
        load_bearing_cell,
        claim.get("aggregate", "PENDING"),
        "; ".join(evidence) or "-",
        "; ".join(counter_cases) or "-",
        adverse_state_cell,
    ]
    return "| " + " | ".join(_escape_pipe(cell) for cell in cells) + " |"


def _escape_pipe(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
