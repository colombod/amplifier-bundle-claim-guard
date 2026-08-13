"""Write-confined JSON persistence for claim-ledger runs.

Writes ONLY under <repo>/<run_dir>/<run_id>/ledger.json. `run_id` is caller-supplied
input, so it is sanitized (no path separators, no dots) and the final resolved path
is verified to sit inside the confinement root before any write -- defense in depth
even if the sanitizer is ever loosened.
"""

from __future__ import annotations

import json
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
        path = self.ledger_file(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=False), encoding="utf-8")

    def new_run_id(self) -> str:
        return "run_" + uuid.uuid4().hex[:8]
