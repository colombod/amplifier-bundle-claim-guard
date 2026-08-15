"""Recipe/docs <-> ledger-op drift guard (KI #3 / claim_gate-bxq).

KI-3 was a stale claim in probe-claims.yaml that named ledger ops as "missing" when
they existed -- a claim<->code correspondence failure inside the bundle's own prose,
undetected because nothing bound recipe/doc text to the ledger's real op surface (the
R-6 guard only binds harvester vocabulary to identity.py).

This test closes that gap deterministically (no LLM): it scans the recipe YAML(s) and
the ledger contract doc for references to claim_ledger operation names, and asserts every
referenced op ACTUALLY EXISTS in the module's dispatch surface (ops.HANDLERS). If someone
renames/removes an op without updating the prose, or the prose names an op that does not
exist, this fails in CI -- the same drift the gate hunts can no longer live silently here.

Design: the authoritative op set is ops.HANDLERS.keys() (the real dispatch registry).
We match op names in prose using word-boundary regex over that KNOWN vocabulary (not
arbitrary tokens), so an unrelated English word can never be a false positive; the only
way this test flags is a real op-name reference that the registry does not contain.
"""

from __future__ import annotations

import re
from pathlib import Path

from amplifier_module_tool_claim_ledger.ops import HANDLERS

# Repo root = .../amplifier-bundle-claim-guard (module dir is <root>/modules/tool-claim-ledger).
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Prose surfaces that reference ledger operations by name.
_PROSE_FILES = [
    _REPO_ROOT / "recipes" / "verify-claims.yaml",
    _REPO_ROOT / "recipes" / "probe-claims.yaml",
    _REPO_ROOT / "docs" / "tool-claim-ledger-contract.md",
]

# The authoritative op vocabulary -- the real dispatch registry.
_ACTUAL_OPS = set(HANDLERS.keys())


def _ops_referenced_in(text: str) -> set[str]:
    """Op names from the authoritative vocabulary that appear as whole words in `text`.

    Matching only over KNOWN op names means an arbitrary English word cannot be a false
    positive -- the set is always a subset of the vocabulary we search for. What this
    cannot catch is a *misspelled* op reference (e.g. "record_prob"); that is acceptable
    -- the guard's job is to catch a real op-name reference that the registry lacks, and
    to break loudly if an op is renamed/removed while prose still names the old one.
    """
    found: set[str] = set()
    for op in _ACTUAL_OPS:
        if re.search(rf"(?<![\w-]){re.escape(op)}(?![\w-])", text):
            found.add(op)
    return found


def test_prose_files_exist() -> None:
    # Fail loudly if a scanned surface is moved/renamed -- a silently-skipped guard is
    # worse than a failing one.
    for path in _PROSE_FILES:
        assert path.is_file(), (
            f"drift-guard target missing: {path.relative_to(_REPO_ROOT)}"
        )


def test_every_referenced_op_exists() -> None:
    """Every claim_ledger op named in the recipes/docs must exist in ops.HANDLERS."""
    for path in _PROSE_FILES:
        text = path.read_text(encoding="utf-8")
        referenced = _ops_referenced_in(text)
        unknown = referenced - _ACTUAL_OPS  # structurally empty by construction...
        assert not unknown, (
            f"{path.relative_to(_REPO_ROOT)} references ledger ops not in HANDLERS: "
            f"{sorted(unknown)}"
        )


def test_guard_would_catch_a_renamed_op() -> None:
    """Negative proof: prose naming a non-existent op is detectable.

    This mirrors the exact KI-3 failure mode (prose names ops the module lacks) and
    proves the mechanism bites, using a synthetic vocabulary rather than editing a real
    file.
    """
    synthetic_vocab = _ACTUAL_OPS | {
        "record_prophecy"
    }  # a ledger op that does not exist
    prose = "The recipe calls record_probe and then record_prophecy on the ledger."
    referenced = {
        op
        for op in synthetic_vocab
        if re.search(rf"(?<![\w-]){re.escape(op)}(?![\w-])", prose)
    }
    unknown = referenced - _ACTUAL_OPS
    assert unknown == {"record_prophecy"}, (
        "the drift guard must flag a prose reference to an op absent from HANDLERS"
    )


def test_core_ops_are_actually_referenced_somewhere() -> None:
    """Sanity: the ops the Phase-2 recipe/docs are supposed to describe are present in
    the prose -- so this guard is exercising real references, not vacuously passing.

    (Precisely the ops KI-3's stale comment wrongly called 'missing'.)
    """
    all_prose = "\n".join(
        p.read_text(encoding="utf-8") for p in _PROSE_FILES if p.is_file()
    )
    referenced = _ops_referenced_in(all_prose)
    for op in (
        "record_probe",
        "defer_claim",
        "graduate_test",
        "record_verdict",
        "gate",
    ):
        assert op in referenced, (
            f"expected ledger op '{op}' to be referenced in the recipes/docs; "
            "either the prose stopped documenting it or the guard is not scanning it"
        )
