"""Atomic save: a crash mid-write must never corrupt or truncate ledger.json.

`LedgerStore.save()` writes to a temp file in the same directory, flushes and
fsyncs it, then `os.replace()`s it into place -- atomic on POSIX. Any reader
sees either the prior complete file or the new complete file, never a partial
one, and the temp file never lingers after a successful save.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from amplifier_module_tool_claim_ledger.store import LedgerStore


def test_save_writes_valid_json_and_leaves_no_tmp_file(store: LedgerStore) -> None:
    record = {"run_id": "run_abc123", "claims": [], "gates": []}
    store.save("run_abc123", record)

    path = store.ledger_file("run_abc123")
    tmp_path = path.parent / f"{path.name}.tmp"

    assert path.exists()
    assert not tmp_path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == record


def test_repeated_saves_leave_exactly_one_final_file_and_no_tmp(
    store: LedgerStore,
) -> None:
    for i in range(5):
        store.save("run_abc123", {"run_id": "run_abc123", "claims": [], "n": i})

    path = store.ledger_file("run_abc123")
    tmp_path = path.parent / f"{path.name}.tmp"

    assert path.exists()
    assert not tmp_path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["n"] == 4


def test_save_cleans_up_tmp_file_on_write_failure(
    store: LedgerStore, repo_root: Path
) -> None:
    """If the write itself fails partway through, the tmp file must not linger
    -- and the prior complete file (if any) must be left untouched."""
    store.save("run_abc123", {"run_id": "run_abc123", "claims": [], "gen": "first"})
    path = store.ledger_file("run_abc123")
    tmp_path = path.parent / f"{path.name}.tmp"

    class _BoomWrite:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def write(self, _content):
            raise OSError("simulated disk failure mid-write")

        def flush(self):
            pass

        def fileno(self):
            return 0

    with patch("builtins.open", return_value=_BoomWrite()), pytest.raises(OSError):
        store.save(
            "run_abc123", {"run_id": "run_abc123", "claims": [], "gen": "second"}
        )

    # Nothing was left behind under the tmp name.
    assert not tmp_path.exists()
    # The prior complete file is untouched (never partially overwritten).
    assert json.loads(path.read_text(encoding="utf-8"))["gen"] == "first"


def test_save_creates_parent_directories(store: LedgerStore) -> None:
    record = {"run_id": "run_fresh", "claims": []}
    store.save("run_fresh", record)

    path = store.ledger_file("run_fresh")
    assert path.parent.is_dir()
    assert path.exists()
