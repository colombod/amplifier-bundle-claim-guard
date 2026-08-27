"""Shared fixtures for tool-claim-ledger tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from amplifier_module_tool_claim_ledger.store import LedgerStore
from amplifier_module_tool_claim_ledger.tool import ClaimLedgerTool


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A throwaway 'repo' directory for confinement tests."""
    return tmp_path


@pytest.fixture
def store(repo_root: Path) -> LedgerStore:
    return LedgerStore(repo_root=repo_root, run_dir=".claim-guard")


@pytest.fixture
def tool(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> ClaimLedgerTool:
    """A ClaimLedgerTool with cwd pinned to the throwaway repo (execute() uses Path.cwd())."""
    monkeypatch.chdir(repo_root)
    return ClaimLedgerTool(config={"run_dir": ".claim-guard"})
