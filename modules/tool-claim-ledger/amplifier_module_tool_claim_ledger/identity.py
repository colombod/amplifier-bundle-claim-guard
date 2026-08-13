"""Stable claim identity (F-9).

claim_id = "clm_" + sha1(normalize(text) + "|" + type + "|" + repo_relpath_of(source))[:8]

Deliberately excludes `inferred`, `basis`, `quote`, line numbers, and the run -- a claim
keeps its identity across re-runs of an evolving PR, and across explicit<->implicit
reclassification. See docs/tool-claim-ledger-contract.md "Stable claim IDs across runs".
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCT = re.compile(r"[.,!?;:]+$")
_TRAILING_LINE_NUMBER = re.compile(r"^(.*):(\d+)$")


def normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip trailing punctuation.

    Trivial rewording (case, spacing, a trailing period) does not fork identity;
    a real change of claim text does.
    """
    normalized = text.strip().lower()
    normalized = _WHITESPACE.sub(" ", normalized)
    normalized = _TRAILING_PUNCT.sub("", normalized)
    return normalized.strip()


def repo_relpath_of(source: str) -> str:
    """Strip a trailing ':<line-number>' component from `source`.

    Line numbers are explicitly excluded from claim identity (F-9), so a claim
    sourced from `docstring:registry.py:88` keeps the same identity component
    as one sourced from `docstring:registry.py:95` after the code shifts. Source
    kinds with no path component (issue:#123, commit:<sha>, pr-body,
    council-verdict:<lens/finding>) are returned unchanged unless they happen to
    end in a bare ':<digits>' token.
    """
    match = _TRAILING_LINE_NUMBER.match(source)
    if match:
        return match.group(1)
    return source


def compute_claim_id(text: str, claim_type: str, source: str) -> str:
    """Compute the base (unsuffixed) stable claim_id for (text, type, source)."""
    identity = f"{normalize_text(text)}|{claim_type}|{repo_relpath_of(source)}"
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()
    return f"clm_{digest[:8]}"


def identity_key(text: str, claim_type: str, source: str) -> tuple[str, str, str]:
    """The tuple used to decide whether two claims sharing a claim_id are the *same*
    claim (idempotent re-add) or a genuine hash collision (disambiguate with -N)."""
    return (normalize_text(text), claim_type, repo_relpath_of(source))
