"""Stable claim IDs (F-9): reword-stable, type-sensitive, run-independent."""

from __future__ import annotations

from amplifier_module_tool_claim_ledger.identity import (
    compute_claim_id,
    normalize_text,
    repo_relpath_of,
)


def test_normalize_collapses_whitespace_and_case() -> None:
    assert (
        normalize_text("  A Degraded   Server\nWill Not Corrupt Data.  ")
        == "a degraded server will not corrupt data"
    )


def test_normalize_strips_trailing_punctuation_only() -> None:
    assert normalize_text("no data loss!!!") == "no data loss"
    assert (
        normalize_text("safe? really?") == "safe? really"
    )  # only *trailing* run is stripped


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


def test_claim_id_is_type_sensitive() -> None:
    """The same text under a different type is a different claim."""
    id_safety = compute_claim_id(
        "MERGE is idempotent", "safety", "docstring:merge.py:10"
    )
    id_correspondence = compute_claim_id(
        "MERGE is idempotent", "correspondence", "docstring:merge.py:10"
    )
    assert id_safety != id_correspondence


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


def test_claim_id_has_expected_prefix_and_length() -> None:
    claim_id = compute_claim_id("some claim", "correspondence", "pr-body")
    assert claim_id.startswith("clm_")
    assert len(claim_id) == len("clm_") + 8
