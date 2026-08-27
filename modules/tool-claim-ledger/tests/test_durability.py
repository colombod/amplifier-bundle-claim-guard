"""Durability: the ledger's location survives cwd drift and is self-describing.

Two related defects this guards against:

1. Re-deriving `Path.cwd()` on every tool call means a run's only durable artifact
   (its ledger.json -- including a BLOCK verdict) can be written under an ephemeral
   cwd (a DTU, /tmp) that no longer exists by the time anyone looks for it.
2. Re-deriving `Path.cwd()` per call also means a cwd change mid-session can split
   one run's writes across two different confinement roots, since a later op would
   silently resolve a different `repo_root` than the one `start_run` used.

The fix: `ClaimLedgerTool` resolves `repo_root` ONCE, at construction time (config
override, else `Path.cwd()` at that moment) -- never per call -- and every run
records its own resolved absolute `ledger_path` at creation time, returned by
`start_run`, `gate`, and `report`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from amplifier_module_tool_claim_ledger.ops import op_add_claim, op_report, op_start_run
from amplifier_module_tool_claim_ledger.store import LedgerStore
from amplifier_module_tool_claim_ledger.tool import ClaimLedgerTool


def _run(coro):
    return asyncio.run(coro)


def test_start_run_returns_absolute_ledger_path(store: LedgerStore) -> None:
    result = op_start_run(store, {})

    assert result["ok"] is True
    ledger_path = Path(result["ledger_path"])
    assert ledger_path.is_absolute()
    assert ledger_path == store.ledger_file(result["run_id"])

    # And it's persisted inside the record itself -- self-describing durability.
    run_record = store.load(result["run_id"])
    assert run_record is not None
    assert run_record["ledger_path"] == result["ledger_path"]
    assert run_record["ledger_root"] == str(store.confinement_root())


def test_report_returns_absolute_ledger_path_matching_start_run(
    store: LedgerStore,
) -> None:
    started = op_start_run(store, {})
    run_id = started["run_id"]
    op_add_claim(
        store,
        {
            "run_id": run_id,
            "text": "returns sorted output",
            "type": "correspondence",
            "source": "pr-body",
        },
    )

    result = op_report(store, {"run_id": run_id})

    assert result["ok"] is True
    assert result["ledger_path"] == started["ledger_path"]
    assert Path(result["ledger_path"]).is_absolute()


def test_ledger_persists_to_stable_configured_root_despite_cwd_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real-world bug: a DTU/container run's cwd is ephemeral and can drift
    between tool calls. Pointing `repo_root` at a stable mounted path via config
    means every call lands in the same place regardless of cwd.
    """
    stable_root = tmp_path / "stable-mount"
    stable_root.mkdir()
    cwd_a = tmp_path / "ephemeral-cwd-a"
    cwd_b = tmp_path / "ephemeral-cwd-b"
    cwd_a.mkdir()
    cwd_b.mkdir()

    monkeypatch.chdir(cwd_a)
    tool = ClaimLedgerTool(
        config={"run_dir": ".claim-guard", "repo_root": str(stable_root)}
    )

    start_result = _run(tool.execute({"operation": "start_run"}))
    assert start_result.success is True
    run_id = start_result.output["run_id"]
    ledger_path = Path(start_result.output["ledger_path"])
    assert ledger_path.is_relative_to(stable_root)

    # Simulate cwd drift between calls (e.g. an orchestrator chdir mid-session).
    monkeypatch.chdir(cwd_b)

    add_result = _run(
        tool.execute(
            {
                "operation": "add_claim",
                "run_id": run_id,
                "text": "x",
                "type": "correspondence",
                "source": "pr-body",
            }
        )
    )
    assert add_result.success is True

    monkeypatch.chdir(tmp_path)
    report_result = _run(tool.execute({"operation": "report", "run_id": run_id}))

    assert report_result.success is True
    assert report_result.output["ledger_path"] == str(ledger_path)
    # Nothing was written under either ephemeral cwd.
    assert not (cwd_a / ".claim-guard").exists()
    assert not (cwd_b / ".claim-guard").exists()
    # Everything landed under the stable configured root.
    assert ledger_path.exists()


def test_ledger_root_resolved_once_at_construction_survives_cwd_drift_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even without a `repo_root` override, `repo_root` is resolved once at
    construction time -- so a cwd change AFTER the tool is constructed can never
    split one run across two confinement roots.
    """
    original_cwd = tmp_path / "cwd-at-construction"
    other_cwd = tmp_path / "cwd-after-drift"
    original_cwd.mkdir()
    other_cwd.mkdir()

    monkeypatch.chdir(original_cwd)
    tool = ClaimLedgerTool(config={"run_dir": ".claim-guard"})

    start_result = _run(tool.execute({"operation": "start_run"}))
    run_id = start_result.output["run_id"]

    # Drift cwd after construction; the tool must keep using the root it resolved
    # at construction time, not re-derive Path.cwd() on this call.
    monkeypatch.chdir(other_cwd)
    gate_result = _run(tool.execute({"operation": "gate", "run_id": run_id}))

    assert gate_result.success is False or gate_result.output.get("ok") is not None
    assert (original_cwd / ".claim-guard" / run_id / "ledger.json").exists()
    assert not (other_cwd / ".claim-guard").exists()
