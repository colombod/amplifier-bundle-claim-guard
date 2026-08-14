"""Stable claim IDs (F-9): reword-stable, type-sensitive, run-independent.

KI-1 hardening (design/ki1-determinism-spec.md §2.5): the invariants below are
asserted directly, per the spec:
  1. idempotent
  2. reword-stable (must collapse)
  3. type-sensitive (must NOT collapse)
  4. source-sensitive but line-drift-stable
  5. distinct-claims-stay-distinct (the over-collapse tripwire, R-1)
  6. prefix/length preserved
"""

from __future__ import annotations

import pytest
from amplifier_module_tool_claim_ledger.identity import (
    compute_claim_id,
    normalize_text,
    repo_relpath_of,
)

# ---------------------------------------------------------------------------
# 1. Idempotent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The code ensures that max_delete is a cap.",
        "A degraded server won't corrupt data.",
        "\u201cNo duplicate Nodes are created.\u201d",
        "admin.py:972 caps deletes",
        "writes cannot happen while degraded",
        "",
        "   ",
    ],
)
def test_normalize_text_is_idempotent(text: str) -> None:
    once = normalize_text(text)
    twice = normalize_text(once)
    assert once == twice


# ---------------------------------------------------------------------------
# 2. Reword-stable -- trivial rewording must collapse to the same normalized
#    text / claim_id.
# ---------------------------------------------------------------------------


def test_normalize_collapses_whitespace_case_and_articles() -> None:
    """Whitespace/case collapse, and the closed-set article filler is removed."""
    assert (
        normalize_text("  A Degraded   Server\nWill Not Corrupt Data.  ")
        == "degraded server will not corrupt data"
    )


def test_normalize_folds_all_punctuation_to_whitespace() -> None:
    """Unlike the old trailing-only strip, ALL punctuation (not just trailing)
    now folds to whitespace -- this supersedes the old
    test_normalize_strips_trailing_punctuation_only behavior."""
    assert normalize_text("no data loss!!!") == "no data loss"
    assert normalize_text("safe? really?") == "safe really"


def test_repo_relpath_of_strips_trailing_line_number() -> None:
    assert repo_relpath_of("docstring:registry.py:88") == "docstring:registry.py"
    assert repo_relpath_of("docstring:registry.py:95") == "docstring:registry.py"


def test_repo_relpath_of_leaves_non_line_sources_untouched() -> None:
    assert repo_relpath_of("issue:#123") == "issue:#123"
    assert repo_relpath_of("pr-body") == "pr-body"
    assert (
        repo_relpath_of("council-verdict:chokepoint-mapper/finding-1")
        == "council-verdict:chokepoint-mapper/finding-1"
    )


def test_claim_id_is_reword_stable() -> None:
    """Trivial rewording (case, spacing, trailing punctuation) does not fork identity."""
    id_a = compute_claim_id(
        "A degraded server will not corrupt data.", "safety", "docstring:registry.py:88"
    )
    id_b = compute_claim_id(
        "a degraded server will not corrupt data", "safety", "docstring:registry.py:95"
    )
    assert id_a == id_b


@pytest.mark.parametrize(
    ("text_a", "text_b", "reason"),
    [
        (
            "A degraded server won't corrupt data.",
            "a degraded server will not corrupt data",
            "contraction <-> expansion",
        ),
        (
            "\u201cA degraded server won\u2019t corrupt data.\u201d",
            "A degraded server won't corrupt data.",
            "curly quotes/apostrophe fold to ASCII, contraction still recognized",
        ),
        (
            "The code ensures that max_delete is a cap.",
            "max_delete is a cap",
            "'the code'/'ensures that' boilerplate stripped",
        ),
        (
            "This change gates writes while degraded.",
            "gates writes while degraded",
            "'this change' boilerplate stripped",
        ),
        (
            "MAX_DELETE is a cap",
            "max_delete is a cap",
            "identifier-case fold (MAX_DELETE <-> max_delete)",
        ),
        (
            "No duplicate Nodes are created.",
            "No duplicate Nodes created",
            "copula 'are' is a filler",
        ),
    ],
)
def test_claim_id_reword_stable_pairs(text_a: str, text_b: str, reason: str) -> None:
    id_a = compute_claim_id(text_a, "safety", "pr-body")
    id_b = compute_claim_id(text_b, "safety", "pr-body")
    assert id_a == id_b, f"expected same id for: {reason}"


def test_claim_id_stable_across_text_embedded_file_line_drift() -> None:
    """A file:line token embedded in the claim *text* (not just `source`) is
    line-drift stable, mirroring repo_relpath_of's handling of `source`."""
    id_before = compute_claim_id("admin.py:972 caps deletes", "quantitative", "pr-body")
    id_after_shift = compute_claim_id(
        "admin.py:1005 caps deletes", "quantitative", "pr-body"
    )
    assert id_before == id_after_shift


# ---------------------------------------------------------------------------
# 3. Type-sensitive -- must NOT collapse.
# ---------------------------------------------------------------------------


def test_claim_id_is_type_sensitive() -> None:
    """The same text under a different type is a different claim."""
    id_safety = compute_claim_id(
        "MERGE is idempotent", "safety", "docstring:merge.py:10"
    )
    id_correspondence = compute_claim_id(
        "MERGE is idempotent", "correspondence", "docstring:merge.py:10"
    )
    assert id_safety != id_correspondence


# ---------------------------------------------------------------------------
# 4. Source-sensitive but line-drift-stable.
# ---------------------------------------------------------------------------


def test_claim_id_is_run_independent_but_source_sensitive() -> None:
    """Same text+type from a genuinely different source is a different claim."""
    id_a = compute_claim_id(
        "caps enforce a maximum", "quantitative", "docstring:admin.py:20"
    )
    id_b = compute_claim_id(
        "caps enforce a maximum", "quantitative", "docstring:registry.py:20"
    )
    assert id_a != id_b


def test_claim_id_stable_across_line_drift_in_same_file() -> None:
    id_before = compute_claim_id(
        "cap enforces max_delete", "quantitative", "docstring:admin.py:972"
    )
    id_after_shift = compute_claim_id(
        "cap enforces max_delete", "quantitative", "docstring:admin.py:1005"
    )
    assert id_before == id_after_shift


# ---------------------------------------------------------------------------
# 5. Distinct-claims-stay-distinct -- the over-collapse tripwire (R-1).
#
# Each pair shares type+source and MUST hash to a different claim_id. If any
# of these ever collapse, `normalize_text` has become over-aggressive and
# `op_add_claim` would silently drop a genuinely distinct claim.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text_a", "text_b", "reason"),
    [
        ("data is corrupted", "data is not corrupted", "negation flip"),
        ("no duplicates", "some duplicates", "quantifier change"),
        ("under 25k", "under 36k", "bound change"),
        ("server corrupts data", "data corrupts server", "subject/object swap"),
        ("max_delete is a cap", "min_age is a cap", "different identifier"),
        (
            "gates writes while degraded",
            "logs writes while degraded",
            "different predicate",
        ),
        (
            "writes cannot happen while degraded",
            "writes can happen while degraded",
            "modal (negated) change",
        ),
        ("gates writes", "does NOT gate writes", "negation via contraction+filler"),
        ("all paths", "one path", "quantifier vs number-word"),
        ("max_delete>=1", "max_delete>=2", "bound value change on a code token"),
    ],
)
def test_claim_id_distinct_for_minimal_pairs(
    text_a: str, text_b: str, reason: str
) -> None:
    id_a = compute_claim_id(text_a, "safety", "docstring:admin.py:10")
    id_b = compute_claim_id(text_b, "safety", "docstring:admin.py:10")
    assert id_a != id_b, f"over-collapse (R-1): {reason} must stay distinct"


def test_never_strip_words_survive_normalization() -> None:
    """Negation, modals, and quantifiers are never removed as fillers."""
    normalized = normalize_text(
        "no writes can happen and not all paths are gated, only some at most"
    )
    for word in ("no", "can", "not", "all", "only", "some", "at", "most"):
        assert word in normalized.split(" "), f"{word!r} must never be stripped"


# ---------------------------------------------------------------------------
# 6. Prefix/length preserved.
# ---------------------------------------------------------------------------


def test_claim_id_has_expected_prefix_and_length() -> None:
    claim_id = compute_claim_id("some claim", "correspondence", "pr-body")
    assert claim_id.startswith("clm_")
    assert len(claim_id) == len("clm_") + 8
