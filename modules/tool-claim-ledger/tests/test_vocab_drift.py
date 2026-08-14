"""Drift guard (R-6): bind the claim-harvesting contract's controlled vocabulary
to the ledger normalizer's sets, so editing one side without the other fails a
TEST -- not just an eyeball review of two files that live in different repos of
the reader's attention.

Background: skills/claim-harvesting/SKILL.md's "The claim contract" section
explicitly states the harvesters and `identity.normalize_text` must never drift
apart -- "the boilerplate you omit here is exactly what the normalizer strips;
the meaning-critical words you keep here are exactly what it preserves." That
sentence is a promise with nothing enforcing it. This file is the enforcement.

How to read a failure here: if this test fails after you edited
`identity.py`'s `_NEVER_STRIP` / `_FILLERS` / `_FILLER_PHRASES` / `_CONTRACTIONS`,
you changed normalizer behavior without updating the contract prose in
SKILL.md (or vice versa) -- update BOTH the mirror below and SKILL.md, in the
same change, and re-run.
"""

from __future__ import annotations

import pytest
from amplifier_module_tool_claim_ledger.identity import (
    _FILLERS,
    _NEVER_STRIP,
    compute_claim_id,
    normalize_text,
)

# ---------------------------------------------------------------------------
# MIRROR of skills/claim-harvesting/SKILL.md "The claim contract" ->
# "Canonical claim-statement form" -> "Controlled vocabulary" (and the
# boilerplate-lead-in bullet just above it).
#
# If you change the contract's controlled vocabulary in SKILL.md, you MUST
# update this mirror to match. If this mirror and identity.py's sets disagree,
# the assertions below fail -- that disagreement IS the drift (R-6).
# ---------------------------------------------------------------------------

# "negation: use `no` / `not` / `never` / `cannot` -- never 'won't', 'isn't',
# 'doesn't'". These words must never be treated as strippable filler --
# stripping one would merge a claim with its negation (the R-1 tripwire).
CONTRACT_NEGATION_WORDS = frozenset({"no", "not", "never", "cannot"})

# "bounds: use `at most N` / `at least N` / `exactly N` / `under N` -- never
# 'no more than', 'up to'". The meaning-critical tokens inside those bound
# phrases (excluding the number itself, which is guarded structurally as a
# code span, not via a word set) must never be strippable filler.
CONTRACT_BOUND_TOKENS = frozenset({"at", "most", "least", "exactly", "under"})

# "No boilerplate lead-ins. Never start with 'the code ensures that...', 'this
# change guarantees...', 'the system will...'. (These lead-ins are exactly
# what the normalizer strips...)" -- the atomic phrases that compose those
# lead-ins and that the normalizer actually removes as a phrase-level pre-pass.
#
# NOTE on granularity: SKILL.md's prose quotes three full sentence-starts, but
# the normalizer strips at the level of six shorter phrase primitives (mirrored
# 1:1 below) that compose those sentence-starts. "the system will..." is a
# case where the composition is *deliberately* incomplete: "the system" is a
# stripped filler phrase, but "will" is a never-touched token (identity.py
# keeps "will" specifically because the KI-1 worked example --
# "won't corrupt data" -> "will not corrupt data" -- requires it to survive
# contraction expansion). So "the system will X" alone does not fully collapse
# to "X"; only the "the system" portion does. That is intentional, documented
# behavior, not something this guard treats as a failure -- asserting full
# collapse of "the system will..." would be over-asserting past what the
# contract and the normalizer actually agree on.
CONTRACT_BOILERPLATE_PHRASES = (
    "the code",
    "this change",
    "the system",
    "ensures that",
    "guarantees that",
    "such that",
)


# ---------------------------------------------------------------------------
# 1. Negation preserved: every contract negation word must never be strippable.
# ---------------------------------------------------------------------------


def test_contract_negation_words_are_all_never_strip() -> None:
    missing = CONTRACT_NEGATION_WORDS - _NEVER_STRIP
    assert not missing, (
        f"Contract negation words {sorted(missing)} are not in "
        "identity._NEVER_STRIP -- the normalizer could fold a claim and its "
        "negation to the same id. Update _NEVER_STRIP (or the contract) to "
        "keep them in sync."
    )


# ---------------------------------------------------------------------------
# 2. Bound tokens preserved: meaning-critical words inside "at most/least/
#    exactly/under N" must never be strippable.
# ---------------------------------------------------------------------------


def test_contract_bound_tokens_are_all_never_strip() -> None:
    missing = CONTRACT_BOUND_TOKENS - _NEVER_STRIP
    assert not missing, (
        f"Contract bound tokens {sorted(missing)} are not in "
        "identity._NEVER_STRIP -- the normalizer could fold a bound claim "
        "and its bound-inverted counterpart to the same id."
    )


# ---------------------------------------------------------------------------
# 3. Never-strip vs filler disjoint -- re-asserted here as a TEST (not just an
#    import-time assertion), so a future edit that violates it fails pytest
#    (and CI) rather than only failing at collection/import time with a bare
#    AssertionError attributed to nothing in particular.
# ---------------------------------------------------------------------------


def test_never_strip_and_fillers_remain_disjoint() -> None:
    overlap = _NEVER_STRIP & _FILLERS
    assert not overlap, (
        f"_NEVER_STRIP and _FILLERS overlap on {sorted(overlap)} -- a "
        "meaning-critical word would be silently stripped as filler."
    )


# ---------------------------------------------------------------------------
# 4. Boilerplate is actually stripped: emitting any one contract boilerplate
#    phrase changes nothing (proves the normalizer strips what the contract
#    tells agents they may omit).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", CONTRACT_BOILERPLATE_PHRASES)
def test_contract_boilerplate_phrase_is_stripped(phrase: str) -> None:
    with_boilerplate = normalize_text(f"{phrase} max_delete caps deletes")
    without_boilerplate = normalize_text("max_delete caps deletes")
    assert with_boilerplate == without_boilerplate, (
        f"Boilerplate phrase {phrase!r} (from the contract's controlled "
        "vocabulary) is no longer stripped by normalize_text -- either "
        "identity._FILLER_PHRASES changed, or the phrase no longer matches "
        "the mirror above. Keep SKILL.md and identity.py in sync."
    )


def test_contract_worked_example_lead_in_is_stripped() -> None:
    """The contract's own worked example (both authors converge on one id)."""
    with_lead_in = normalize_text("The code ensures that `max_delete` is a cap.")
    without_lead_in = normalize_text("`max_delete` is a cap")
    assert with_lead_in == without_lead_in


# ---------------------------------------------------------------------------
# 5. Golden equivalence classes collapse (reword-stable, from the contract).
# ---------------------------------------------------------------------------

EQUIVALENT_PHRASING_PAIRS = (
    # The contract's own worked example: boilerplate lead-in vs bare form.
    (
        "The code ensures that `max_delete` is a cap.",
        "`max_delete` is a cap",
    ),
    # Negation-canonicalization: contraction form must converge with the
    # controlled-vocabulary "does not" form (contract: never "doesn't").
    (
        "`schema_health` does not gate the write",
        "`schema_health` doesn't gate the write",
    ),
)


@pytest.mark.parametrize(("phrasing_a", "phrasing_b"), EQUIVALENT_PHRASING_PAIRS)
def test_equivalent_phrasings_collapse_to_same_claim_id(
    phrasing_a: str, phrasing_b: str
) -> None:
    id_a = compute_claim_id(phrasing_a, "correspondence", "docstring:mod.py")
    id_b = compute_claim_id(phrasing_b, "correspondence", "docstring:mod.py")
    assert id_a == id_b, (
        f"{phrasing_a!r} and {phrasing_b!r} were supposed to converge to the "
        "same claim_id per the contract's controlled vocabulary, but "
        f"produced {id_a!r} != {id_b!r}."
    )


# ---------------------------------------------------------------------------
# 6. Distinctness still holds (tie-in to R-1): a claim and its negation must
#    NOT collapse, even though the drift guard above proves the normalizer
#    is permissive about phrasing. This is the other half of the same
#    invariant: reword-stable, but never over-collapsing.
# ---------------------------------------------------------------------------


def test_claim_and_its_negation_stay_distinct() -> None:
    positive_id = compute_claim_id(
        "`schema_health` gates the write", "safety", "docstring:mod.py"
    )
    negated_id = compute_claim_id(
        "`schema_health` does not gate the write", "safety", "docstring:mod.py"
    )
    assert positive_id != negated_id, (
        "A claim and its negation collapsed to the same claim_id -- this is "
        "exactly the over-collapse the R-1 tripwire and this R-6 drift guard "
        "both exist to prevent."
    )
