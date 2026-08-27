"""Roster-derived lens-coverage gap (closes the silent lens-coverage hole).

See docs/tool-claim-ledger-contract.md "declare_roster". Mirrors
test_lens_errors.py's structure and the shared `store` fixture. Every case is
deterministic and LLM-free.

THE INCIDENT (test 1, headline): a real run had `chokepoint-mapper` -- a
rostered, mandatory-for-that-claim-type lens -- silently skip exactly one
claim. It called neither `record_verdict` nor `record_lens_error`. Before this
module existed, the gate reported a clean PASS with zero trace anywhere in the
durable record that the lens never looked -- full, clean coverage, by its own
account, despite chokepoint-mapper never having recorded anything for that
claim. That green IS the bug. Test 1 below proves the fix: the identical
scenario, now with a roster declared, gates INDETERMINATE with a
`lens-coverage-gap` reason naming exactly the lens and claim that were
silently skipped.
"""

from __future__ import annotations

import pytest

from amplifier_module_tool_claim_ledger.aggregate import compute_aggregate
from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_aggregate,
    op_declare_roster,
    op_gate,
    op_list_claims,
    op_record_lens_error,
    op_record_verdict,
    op_start_run,
)
from amplifier_module_tool_claim_ledger.roster import CLAIM_TYPES
from amplifier_module_tool_claim_ledger.store import LedgerStore
from amplifier_module_tool_claim_ledger.tool import ClaimLedgerTool


def _add(
    store: LedgerStore, run_id: str, text: str, claim_type: str, source: str
) -> tuple[str, str]:
    if not run_id:
        run_id = op_start_run(store, {})["run_id"]
    result = op_add_claim(
        store, {"run_id": run_id, "text": text, "type": claim_type, "source": source}
    )
    assert result["ok"] is True
    return result["run_id"], result["claim_id"]


def _confirm(
    store: LedgerStore,
    run_id: str,
    claim_id: str,
    lens: str,
    anchor: str,
    adverse_state: bool = True,
) -> None:
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": lens,
            "verdict": "CONFIRMED",
            "evidence": [anchor],
            "adverse_state_test": {
                "exists": adverse_state,
                "test_ref": f"test_{lens}" if adverse_state else None,
                "reason": "graduated probe" if adverse_state else None,
            },
        },
    )
    assert result["ok"] is True


def _claim(store: LedgerStore, run_id: str, claim_id: str) -> dict:
    listed = op_list_claims(store, {"run_id": run_id})
    return next(c for c in listed["claims"] if c["claim_id"] == claim_id)


# --------------------------------------------------------------------------- #
# 1. THE INCIDENT (headline test)
# --------------------------------------------------------------------------- #


def test_rostered_lens_that_skips_one_claim_is_a_coverage_gap(
    store: LedgerStore,
) -> None:
    run_id, claim1 = _add(
        store,
        "",
        "a degraded server will not corrupt data",
        "safety",
        "docstring:a.py:1",
    )
    _, claim2 = _add(
        store,
        run_id,
        "a stale cache entry will not serve corrupted reads",
        "safety",
        "docstring:b.py:1",
    )

    roster_result = op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": ["correspondence-auditor"],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "2 claims name a guard/prevention mechanism",
                }
            },
            "declared_by": "test",
        },
    )
    assert roster_result["ok"] is True

    # claim 1: BOTH rostered lenses run.
    _confirm(store, run_id, claim1, "correspondence-auditor", "a.py:10")
    _confirm(store, run_id, claim1, "chokepoint-mapper", "a.py:20")

    # claim 2: chokepoint-mapper SILENTLY SKIPS -- no record_verdict, no
    # record_lens_error. This is the incident.
    _confirm(store, run_id, claim2, "correspondence-auditor", "b.py:10")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "INDETERMINATE"
    assert (
        f"lens-coverage-gap:chokepoint-mapper@{claim2}"
        in result["indeterminate_reasons"]
    )
    assert not any(
        r == f"lens-coverage-gap:chokepoint-mapper@{claim1}"
        for r in result["indeterminate_reasons"]
    )
    # The gap does not rewrite verdicts -- claim 2 is still CONFIRMED.
    assert _claim(store, run_id, claim2)["aggregate"] == "CONFIRMED"
    assert result["coverage"]["lens_covered"] == 3
    assert result["coverage"]["lens_expected"] == 4


# --------------------------------------------------------------------------- #
# Backward compat / default
# --------------------------------------------------------------------------- #


def test_no_roster_declared_is_indeterminate(store: LedgerStore) -> None:
    run_id, claim_id = _add(
        store, "", "returns sorted output", "correspondence", "pr-body"
    )
    _confirm(store, run_id, claim_id, "correspondence-auditor", "sort.py:12")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "INDETERMINATE"
    assert "no-roster-declared" in result["indeterminate_reasons"]
    assert result["coverage"]["lens_covered"] is None
    assert result["coverage"]["lens_expected"] is None


def test_zero_claims_does_not_also_emit_no_roster_declared(store: LedgerStore) -> None:
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {"run_id": run_id, "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    run_id = added["run_id"]
    run_record = store.load(run_id)
    assert run_record is not None
    run_record["claims"] = []
    store.save(run_id, run_record)

    result = op_gate(store, {"run_id": run_id})

    assert result["indeterminate_reasons"] == ["zero-claims-harvested"]
    assert "no-roster-declared" not in result["indeterminate_reasons"]


def test_empty_declared_roster_is_the_opt_out(store: LedgerStore) -> None:
    run_id, claim_id = _add(
        store, "", "returns sorted output", "correspondence", "pr-body"
    )
    declared = op_declare_roster(
        store, {"run_id": run_id, "mandatory": [], "conditional": {}}
    )
    assert declared["ok"] is True
    _confirm(store, run_id, claim_id, "correspondence-auditor", "sort.py:12")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "PASS"
    assert not any(
        r.startswith(
            ("lens-coverage-gap", "roster-inconsistency", "no-roster-declared")
        )
        for r in result["indeterminate_reasons"]
    )
    assert result["coverage"]["lens_expected"] == 0


def test_pre_existing_ledger_without_roster_key_loads_and_gates(
    store: LedgerStore,
) -> None:
    run_id = op_start_run(store, {})["run_id"]
    added = op_add_claim(
        store,
        {"run_id": run_id, "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    run_id = added["run_id"]
    run_record = store.load(run_id)
    assert run_record is not None
    del run_record["roster"]
    del run_record["roster_history"]
    store.save(run_id, run_record)

    result = op_gate(store, {"run_id": run_id})

    assert result["ok"] is True
    assert result["verdict"] == "INDETERMINATE"
    assert "no-roster-declared" in result["indeterminate_reasons"]


# --------------------------------------------------------------------------- #
# Under-declaration / anti-shrink
# --------------------------------------------------------------------------- #


def test_lens_verdict_outside_roster_is_a_roster_inconsistency(
    store: LedgerStore,
) -> None:
    run_id, claim_id = _add(
        store, "", "returns sorted output", "correspondence", "pr-body"
    )
    op_declare_roster(
        store, {"run_id": run_id, "mandatory": ["correspondence-auditor"]}
    )

    # boundary-adversary is not rostered for this claim at all.
    result = op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "verdict": "CONFIRMED",
            "evidence": ["sort.py:12"],
        },
    )
    assert result["ok"] is True
    _confirm(store, run_id, claim_id, "correspondence-auditor", "sort.py:12")

    gate_result = op_gate(store, {"run_id": run_id})

    assert gate_result["verdict"] == "INDETERMINATE"
    assert (
        f"roster-inconsistency:boundary-adversary@{claim_id}"
        in gate_result["indeterminate_reasons"]
    )
    # The verdict is still recorded and still counted by worst-wins.
    assert _claim(store, run_id, claim_id)["aggregate"] == "CONFIRMED"


def test_shrinking_the_roster_to_hide_a_gap_creates_inconsistencies(
    store: LedgerStore,
) -> None:
    run_id, c1 = _add(store, "", "claim one", "correspondence", "pr-body")
    _, c2 = _add(store, run_id, "claim two", "correspondence", "pr-body")
    _, c3 = _add(store, run_id, "claim three", "correspondence", "pr-body")

    op_declare_roster(
        store,
        {"run_id": run_id, "mandatory": ["correspondence-auditor", "second-lens"]},
    )

    # second-lens covers only 2 of 3 claims -> 1 gap (on c3).
    _confirm(store, run_id, c1, "correspondence-auditor", "a.py:1")
    _confirm(store, run_id, c1, "second-lens", "a.py:2")
    _confirm(store, run_id, c2, "correspondence-auditor", "b.py:1")
    _confirm(store, run_id, c2, "second-lens", "b.py:2")
    _confirm(store, run_id, c3, "correspondence-auditor", "c.py:1")

    first_gate = op_gate(store, {"run_id": run_id})
    assert first_gate["verdict"] == "INDETERMINATE"
    assert f"lens-coverage-gap:second-lens@{c3}" in first_gate["indeterminate_reasons"]

    # Shrink the roster to drop second-lens entirely -- hiding the gap on c3...
    redeclared = op_declare_roster(
        store, {"run_id": run_id, "mandatory": ["correspondence-auditor"]}
    )
    assert redeclared["ok"] is True

    second_gate = op_gate(store, {"run_id": run_id})
    assert second_gate["verdict"] == "INDETERMINATE"
    assert not any(
        r.startswith("lens-coverage-gap") for r in second_gate["indeterminate_reasons"]
    )
    # ...but creates 2 inconsistencies (c1 and c2, where second-lens DID verdict).
    inconsistencies = [
        r
        for r in second_gate["indeterminate_reasons"]
        if r.startswith("roster-inconsistency")
    ]
    assert set(inconsistencies) == {
        f"roster-inconsistency:second-lens@{c1}",
        f"roster-inconsistency:second-lens@{c2}",
    }


def test_redeclaring_pushes_prior_roster_to_history(store: LedgerStore) -> None:
    run_id, _claim_id = _add(store, "", "claim one", "correspondence", "pr-body")

    first = op_declare_roster(
        store, {"run_id": run_id, "mandatory": ["correspondence-auditor"]}
    )
    assert first["replaced"] is False

    second = op_declare_roster(
        store,
        {"run_id": run_id, "mandatory": ["correspondence-auditor", "second-lens"]},
    )
    assert second["replaced"] is True

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["roster_history"]) == 1
    assert run_record["roster_history"][0] == first["roster"]


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("claim_type", sorted(CLAIM_TYPES))
def test_mandatory_lens_expected_on_every_claim_type(
    store: LedgerStore, claim_type: str
) -> None:
    run_id, claim_id = _add(store, "", "some claim", claim_type, "pr-body")
    declared = op_declare_roster(
        store, {"run_id": run_id, "mandatory": ["correspondence-auditor"]}
    )
    row = next(e for e in declared["expected"] if e["claim_id"] == claim_id)
    assert row["expected_lenses"] == ["correspondence-auditor"]


def test_conditional_lens_expected_only_on_trigger_types(store: LedgerStore) -> None:
    run_id, safety_claim = _add(store, "", "safety claim", "safety", "pr-body")
    _, coverage_claim = _add(store, run_id, "coverage claim", "coverage", "pr-body")

    declared = op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": [],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "safety trigger",
                }
            },
        },
    )
    expected_by_claim = {
        e["claim_id"]: e["expected_lenses"] for e in declared["expected"]
    }
    assert expected_by_claim[safety_claim] == ["chokepoint-mapper"]
    assert expected_by_claim[coverage_claim] == []


def test_excluded_conditional_lens_is_never_expected(store: LedgerStore) -> None:
    run_id, claim_id = _add(store, "", "safety claim", "safety", "pr-body")
    declared = op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": [],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": False,
                    "reason": "no guard/gate mechanism named",
                }
            },
        },
    )
    row = next(e for e in declared["expected"] if e["claim_id"] == claim_id)
    assert row["expected_lenses"] == []

    _confirm(store, run_id, claim_id, "correspondence-auditor", "a.py:1")
    result = op_gate(store, {"run_id": run_id})
    assert not any(
        r.startswith("lens-coverage-gap") for r in result["indeterminate_reasons"]
    )


def test_retyping_a_claim_reroutes_expectation(store: LedgerStore) -> None:
    """Proves LAZY derivation -- the Gate-A retype case that would kill a
    frozen-at-add-time per-claim expected-lens list."""
    run_id, claim_id = _add(store, "", "some claim", "correspondence", "pr-body")
    op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": [],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "safety trigger",
                }
            },
        },
    )
    _confirm(store, run_id, claim_id, "correspondence-auditor", "a.py:1")

    before = op_gate(store, {"run_id": run_id})
    assert not any(
        r.startswith("lens-coverage-gap") for r in before["indeterminate_reasons"]
    )

    # Gate-A retype: a human reclassifies the claim from correspondence -> safety.
    run_record = store.load(run_id)
    assert run_record is not None
    claim = next(c for c in run_record["claims"] if c["claim_id"] == claim_id)
    claim["type"] = "safety"
    store.save(run_id, run_record)

    after = op_gate(store, {"run_id": run_id})
    assert (
        f"lens-coverage-gap:chokepoint-mapper@{claim_id}"
        in after["indeterminate_reasons"]
    )


# --------------------------------------------------------------------------- #
# Lens errors interact correctly
# --------------------------------------------------------------------------- #


def test_lens_error_counts_as_coverage_not_as_a_gap(store: LedgerStore) -> None:
    run_id, claim_id = _add(store, "", "safety claim", "safety", "pr-body")
    op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": ["correspondence-auditor"],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "safety trigger",
                }
            },
        },
    )
    _confirm(store, run_id, claim_id, "correspondence-auditor", "a.py:1")
    op_record_lens_error(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "chokepoint-mapper",
            "error": "LSP server crashed mid-trace",
        },
    )

    result = op_gate(store, {"run_id": run_id})

    assert f"lens-error:chokepoint-mapper@{claim_id}" in result["indeterminate_reasons"]
    assert not any(
        r.startswith("lens-coverage-gap") for r in result["indeterminate_reasons"]
    )
    assert result["coverage"]["lens_covered"] == 2
    assert result["coverage"]["lens_expected"] == 2


def test_pending_claim_emits_both_pending_and_per_lens_gaps(store: LedgerStore) -> None:
    run_id, claim_id = _add(store, "", "safety claim", "safety", "pr-body")
    op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": ["correspondence-auditor"],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "safety trigger",
                }
            },
        },
    )

    result = op_gate(store, {"run_id": run_id})

    reasons = set(result["indeterminate_reasons"])
    assert f"claim-pending:{claim_id}" in reasons
    assert f"lens-coverage-gap:correspondence-auditor@{claim_id}" in reasons
    assert f"lens-coverage-gap:chokepoint-mapper@{claim_id}" in reasons
    assert len(reasons) == 3


# --------------------------------------------------------------------------- #
# Validation (each asserts nothing was written)
# --------------------------------------------------------------------------- #


def test_declare_roster_rejects_unknown_claim_type(store: LedgerStore) -> None:
    run_id, _claim_id = _add(store, "", "x", "correspondence", "pr-body")

    result = op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": [],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safey"],
                    "included": True,
                    "reason": "typo'd type",
                }
            },
        },
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_input"
    assert "unknown claim type" in result["message"]
    run_record = store.load(run_id)
    assert run_record is not None
    assert run_record["roster"] is None


@pytest.mark.parametrize("included", [True, False])
def test_declare_roster_rejects_conditional_entry_without_reason(
    store: LedgerStore, included: bool
) -> None:
    run_id, _claim_id = _add(store, "", "x", "correspondence", "pr-body")

    result = op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": [],
            "conditional": {
                "chokepoint-mapper": {"types": ["safety"], "included": included}
            },
        },
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_input"
    run_record = store.load(run_id)
    assert run_record is not None
    assert run_record["roster"] is None


def test_declare_roster_rejects_lens_in_both_mandatory_and_conditional(
    store: LedgerStore,
) -> None:
    run_id, _claim_id = _add(store, "", "x", "correspondence", "pr-body")

    result = op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": ["chokepoint-mapper"],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "x",
                }
            },
        },
    )
    assert result["ok"] is False
    assert result["error"] == "invalid_input"
    assert "chokepoint-mapper" in result["message"]
    run_record = store.load(run_id)
    assert run_record is not None
    assert run_record["roster"] is None


def test_declare_roster_rejects_unknown_run_id(store: LedgerStore) -> None:
    result = op_declare_roster(
        store, {"run_id": "run_doesnotexist", "mandatory": ["correspondence-auditor"]}
    )
    assert result["ok"] is False
    assert result["error"] == "run_not_found"


def test_declare_roster_echoes_expected_lenses_per_claim(store: LedgerStore) -> None:
    run_id, claim_id = _add(store, "", "safety claim", "safety", "pr-body")

    result = op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": ["correspondence-auditor"],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "safety trigger",
                }
            },
        },
    )
    assert result["ok"] is True
    row = next(e for e in result["expected"] if e["claim_id"] == claim_id)
    assert row["type"] == "safety"
    assert row["expected_lenses"] == ["chokepoint-mapper", "correspondence-auditor"]


# --------------------------------------------------------------------------- #
# Policy + non-regression
# --------------------------------------------------------------------------- #


def test_advisory_does_not_downgrade_a_coverage_gap(store: LedgerStore) -> None:
    run_id, claim_id = _add(store, "", "safety claim", "safety", "pr-body")
    op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": ["correspondence-auditor"],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "safety trigger",
                }
            },
        },
    )
    _confirm(store, run_id, claim_id, "correspondence-auditor", "a.py:1")

    result = op_gate(store, {"run_id": run_id, "gate_policy": "advisory"})

    assert result["verdict"] == "INDETERMINATE"
    assert (
        f"lens-coverage-gap:chokepoint-mapper@{claim_id}"
        in result["indeterminate_reasons"]
    )


def test_coverage_gap_never_produces_a_blocking_claim(store: LedgerStore) -> None:
    run_id, claim_id = _add(store, "", "safety claim", "safety", "pr-body")
    op_declare_roster(
        store,
        {
            "run_id": run_id,
            "mandatory": ["correspondence-auditor"],
            "conditional": {
                "chokepoint-mapper": {
                    "types": ["safety"],
                    "included": True,
                    "reason": "safety trigger",
                }
            },
        },
    )
    _confirm(store, run_id, claim_id, "correspondence-auditor", "a.py:1")

    result = op_gate(store, {"run_id": run_id})

    assert result["verdict"] == "INDETERMINATE"
    assert result["blocking_claims"] == []


def test_worst_wins_is_unchanged_by_roster(store: LedgerStore) -> None:
    """Re-run a representative test_aggregate.py case with a roster present --
    identical aggregates. Roster coverage is orthogonal to worst-wins."""
    run_id, claim_id = _add(
        store, "", "cap enforced", "quantitative", "docstring:a.py:10"
    )
    op_declare_roster(
        store, {"run_id": run_id, "mandatory": ["correspondence-auditor"]}
    )

    _confirm(store, run_id, claim_id, "correspondence-auditor", "a.py:1")
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "boundary-adversary",
            "verdict": "REFUTED",
            "evidence": ["a.py:2"],
            "counter_case": "max_delete=0 disables the cap",
        },
    )

    aggregated = op_aggregate(store, {"run_id": run_id})
    claim_view = next(c for c in aggregated["claims"] if c["claim_id"] == claim_id)
    assert claim_view["aggregate"] == "REFUTED"
    assert claim_view["aggregate"] == compute_aggregate(
        [
            {"lens": "correspondence-auditor", "verdict": "CONFIRMED"},
            {"lens": "boundary-adversary", "verdict": "REFUTED"},
        ]
    )


# --------------------------------------------------------------------------- #
# Tool wiring sanity (declare_roster is a real dispatched operation)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_declare_roster_is_dispatched_by_the_tool(tool: ClaimLedgerTool) -> None:
    start = await tool.execute(
        {
            "operation": "add_claim",
            "run_id": (await tool.execute({"operation": "start_run"})).output["run_id"],
            "text": "x",
            "type": "correspondence",
            "source": "pr-body",
        }
    )
    run_id = start.output["run_id"]

    result = await tool.execute(
        {
            "operation": "declare_roster",
            "run_id": run_id,
            "mandatory": ["correspondence-auditor"],
        }
    )
    assert result.success is True
    assert result.output["ok"] is True
    assert result.output["roster"]["mandatory"] == ["correspondence-auditor"]
