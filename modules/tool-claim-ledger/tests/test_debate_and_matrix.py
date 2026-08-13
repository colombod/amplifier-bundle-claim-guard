"""record_debate (auditable relay) and render_matrix (markdown/json)."""

from __future__ import annotations

import json

from amplifier_module_tool_claim_ledger.ops import (
    op_add_claim,
    op_record_debate,
    op_record_verdict,
    op_render_matrix,
)
from amplifier_module_tool_claim_ledger.store import LedgerStore


def test_record_debate_persists_verbatim_relay(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    run_id = added["run_id"]

    result = op_record_debate(
        store,
        {
            "run_id": run_id,
            "round": 2,
            "to_lens": "correspondence-auditor",
            "relayed_payload": "chokepoint-mapper found registry.py:648 is one branch over",
            "from_lenses": ["chokepoint-mapper"],
        },
    )

    assert result["ok"] is True
    assert result["round"] == 2
    assert result["to_lens"] == "correspondence-auditor"

    run_record = store.load(run_id)
    assert run_record is not None
    assert len(run_record["debate"]) == 1
    entry = run_record["debate"][0]
    assert (
        entry["relayed_payload"]
        == "chokepoint-mapper found registry.py:648 is one branch over"
    )
    assert entry["from_lenses"] == ["chokepoint-mapper"]


def test_render_matrix_json_round_trips_run_record(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    run_id = added["run_id"]

    result = op_render_matrix(store, {"run_id": run_id, "format": "json"})

    assert result["ok"] is True
    parsed = json.loads(result["content"])
    assert parsed["run_id"] == run_id


def test_render_matrix_markdown_includes_verdict_and_coverage_line(
    store: LedgerStore,
) -> None:
    added = op_add_claim(
        store,
        {
            "run_id": "",
            "text": "a degraded server will not corrupt data",
            "type": "safety",
            "source": "docstring:registry.py:88",
        },
    )
    run_id, claim_id = added["run_id"], added["claim_id"]
    op_record_verdict(
        store,
        {
            "run_id": run_id,
            "claim_id": claim_id,
            "lens": "correspondence-auditor",
            "verdict": "CONFIRMED",
            "evidence": ["registry.py:648"],
        },
    )

    result = op_render_matrix(store, {"run_id": run_id, "format": "markdown"})

    assert result["ok"] is True
    assert "a degraded server will not corrupt data" in result["content"]
    assert "CONFIRMED" in result["content"]
    assert "registry.py:648" in result["content"]
    assert "Coverage: harvested=1" in result["content"]


def test_render_matrix_invalid_format_rejected(store: LedgerStore) -> None:
    added = op_add_claim(
        store,
        {"run_id": "", "text": "x", "type": "correspondence", "source": "pr-body"},
    )
    run_id = added["run_id"]

    result = op_render_matrix(store, {"run_id": run_id, "format": "yaml"})

    assert result["ok"] is False
    assert result["error"] == "invalid_format"


def test_render_matrix_unknown_run_id_rejected(store: LedgerStore) -> None:
    result = op_render_matrix(
        store, {"run_id": "run_doesnotexist", "format": "markdown"}
    )
    assert result["ok"] is False
    assert result["error"] == "run_not_found"
