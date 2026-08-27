"""Write-confined JSON persistence for claim-ledger runs.

Writes ONLY under <repo>/<run_dir>/<run_id>/ledger.json. `run_id` is caller-supplied
input, so it is sanitized (no path separators, no dots) and the final resolved path
is verified to sit inside the confinement root before any write -- defense in depth
even if the sanitizer is ever loosened.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

_RUN_ID_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


class WriteConfinementError(Exception):
    """Raised when a run_id or resolved path would escape the confined ledger directory."""


class LedgerStore:
    """Loads/saves ledger run records, confined to <repo>/<run_dir>/<run_id>/ledger.json."""

    def __init__(self, repo_root: Path, run_dir: str = ".claim-guard") -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.run_dir_name = run_dir

    def _confinement_root(self) -> Path:
        return (self.repo_root / self.run_dir_name).resolve()

    def confinement_root(self) -> Path:
        """Public accessor for the resolved directory that scopes every write.

        Callers persist this (see `ledger_root` in the run record) so a run's
        durable location is self-describing rather than re-derivable only by
        re-running the (possibly different) cwd resolution that created it.
        """
        return self._confinement_root()

    def sanitize_run_id(self, run_id: str) -> str:
        if not run_id or not _RUN_ID_SAFE.match(run_id):
            raise WriteConfinementError(f"invalid run_id: {run_id!r}")
        return run_id

    def run_path(self, run_id: str) -> Path:
        safe_id = self.sanitize_run_id(run_id)
        confinement = self._confinement_root()
        candidate = (confinement / safe_id).resolve()
        try:
            candidate.relative_to(confinement)
        except ValueError as exc:
            raise WriteConfinementError(
                f"resolved path escapes confinement root: {candidate}"
            ) from exc
        return candidate

    def ledger_file(self, run_id: str) -> Path:
        return self.run_path(run_id) / "ledger.json"

    def load(self, run_id: str) -> dict[str, Any] | None:
        path = self.ledger_file(run_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, run_id: str, record: dict[str, Any]) -> None:
        """Atomically write the run record to ledger.json.

        A run's ledger is the only durable artifact of a claim-guard run --
        including a BLOCK verdict -- so a crash mid-write must never leave a
        truncated or corrupted `ledger.json` behind. Writes go to a temp file
        in the SAME directory first, are flushed and `fsync`'d to disk, and
        are then moved into place via `os.replace` -- atomic on POSIX, so any
        reader always sees either the prior complete file or the new complete
        file, never a partial one. The temp file is removed on any failure
        before the replace.
        """
        path = self.ledger_file(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.parent / f"{path.name}.tmp"
        content = json.dumps(record, indent=2, sort_keys=False)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def new_run_id(self) -> str:
        return "run_" + uuid.uuid4().hex[:8]

    def list_run_ids(self) -> list[str]:
        """Enumerate existing run_ids under the confinement root.

        Read-only: never creates the confinement root or any run directory.
        A run_id is any immediate subdirectory of the confinement root that
        contains a `ledger.json` file. If the confinement root does not
        exist, returns an empty list rather than raising.
        """
        confinement = self._confinement_root()
        if not confinement.is_dir():
            return []
        run_ids = [
            entry.name
            for entry in confinement.iterdir()
            if entry.is_dir() and (entry / "ledger.json").is_file()
        ]
        return sorted(run_ids)
