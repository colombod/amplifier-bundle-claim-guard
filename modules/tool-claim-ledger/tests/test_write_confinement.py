"""Write confinement: the tool writes only under <repo>/<run_dir>/<run_id>/."""

from __future__ import annotations

from pathlib import Path

import pytest

from amplifier_module_tool_claim_ledger.store import LedgerStore, WriteConfinementError


def test_ledger_file_resolves_inside_confinement_root(repo_root: Path) -> None:
    ledger_store = LedgerStore(repo_root=repo_root, run_dir=".claim-guard")
    path = ledger_store.ledger_file("run_abc123")

    confinement_root = (repo_root / ".claim-guard").resolve()
    assert path.is_relative_to(confinement_root)
    assert path == confinement_root / "run_abc123" / "ledger.json"


def test_save_only_creates_files_under_confinement_root(repo_root: Path) -> None:
    ledger_store = LedgerStore(repo_root=repo_root, run_dir=".claim-guard")
    ledger_store.save("run_abc123", {"run_id": "run_abc123", "claims": []})

    created = sorted(p for p in repo_root.rglob("*") if p.is_file())
    assert len(created) == 1
    assert created[0] == (repo_root / ".claim-guard" / "run_abc123" / "ledger.json")


@pytest.mark.parametrize(
    "malicious_run_id",
    [
        "../../etc/passwd",
        "..",
        "../escape",
        "run/with/slash",
        "run\\with\\backslash",
        "",
    ],
)
def test_path_traversal_run_ids_are_rejected(
    repo_root: Path, malicious_run_id: str
) -> None:
    ledger_store = LedgerStore(repo_root=repo_root, run_dir=".claim-guard")
    with pytest.raises(WriteConfinementError):
        ledger_store.ledger_file(malicious_run_id)


def test_tool_execute_surfaces_write_confinement_violation_as_tool_result(
    tool, repo_root: Path
) -> None:
    import asyncio

    result = asyncio.run(
        tool.execute(
            {
                "operation": "add_claim",
                "run_id": "../escape",
                "text": "x",
                "type": "correspondence",
                "source": "pr-body",
            }
        )
    )

    assert result.success is False
    assert result.output["error"] == "write_confinement_violation"

    # And nothing escaped onto the filesystem outside the repo.
    assert not (repo_root.parent / "escape").exists()
