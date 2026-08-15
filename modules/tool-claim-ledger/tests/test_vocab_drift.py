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


# ===========================================================================
# KI-1 PATH (a) -- the rigid claim template.
#
# MIRROR of skills/claim-harvesting/SKILL.md "The claim contract" ->
# "Rule 2 -- PHRASING: the rigid claim template". The prompt prong now carries
# reproducibility alone (temperature:0 is inert on the Opus-4.7+ harvest
# routing), so every claim's text is the fixed three-slot template
#     <mechanism_symbol> <controlled_verb> <controlled_property_object>
# and the (verb, object, type) are fixed by the cell's property. This section
# binds that closed vocabulary to the normalizer, so editing the contract's
# tables without updating this mirror (or vice versa) fails a TEST.
#
# If you add / rename / retire a controlled verb, property object, or the
# property->type map in SKILL.md, update the mirror below in the SAME change.
# ===========================================================================

# property -> (controlled_verb, controlled_property_object, claim_type)
CONTRACT_PREDICATE: dict[str, tuple[str, str, str]] = {
    "corruption": ("preserves", "integrity", "safety"),
    "loss": ("persists", "writes", "safety"),
    "inversion": ("rejects", "inversion", "safety"),
    "staleness": ("refreshes", "state", "temporal"),
    "bound_quantity": ("caps", "quantity", "quantitative"),
    "idempotence": ("deduplicates", "effects", "concurrency"),
    "coverage": ("covers", "behavior", "coverage"),
}

CONTRACT_PROPERTY_ENUM = frozenset(CONTRACT_PREDICATE)
CONTRACT_TEMPLATE_VERBS = frozenset(v for v, _o, _t in CONTRACT_PREDICATE.values())
CONTRACT_PROPERTY_OBJECTS = frozenset(o for _v, o, _t in CONTRACT_PREDICATE.values())

# The claim `type` enum the ledger accepts (mirrors ops.py / the contract).
VALID_CLAIM_TYPES = frozenset(
    {"correspondence", "safety", "quantitative", "temporal", "concurrency", "coverage"}
)

# Realistic snake_case symbols -- unambiguously code spans, casefold to
# themselves, and never fillers (a single-letter symbol like "a" would be a
# filler, which real diff symbols never are).
_SAMPLE_SYMBOLS = ("alpha_sym", "beta_sym", "max_delete", "schema_health")


# ---------------------------------------------------------------------------
# 7. The template's controlled verbs and objects must survive normalization --
#    i.e. none may be a filler. If one were, the template token would be
#    silently dropped and two distinct cells could collapse (over-collapse) or
#    the id would not match run-to-run (under-collapse). Either way the
#    prompt<->normalizer agreement the template relies on would be broken.
# ---------------------------------------------------------------------------


def test_template_verbs_are_never_fillers() -> None:
    offenders = CONTRACT_TEMPLATE_VERBS & _FILLERS
    assert not offenders, (
        f"Controlled template verbs {sorted(offenders)} are in identity._FILLERS "
        "-- normalize_text would strip them, breaking the template's byte-canonical "
        "agreement with the normalizer. Keep SKILL.md's verb set and identity.py in sync."
    )


def test_template_property_objects_are_never_fillers() -> None:
    offenders = CONTRACT_PROPERTY_OBJECTS & _FILLERS
    assert not offenders, (
        f"Controlled property objects {sorted(offenders)} are in identity._FILLERS "
        "-- normalize_text would strip them, breaking the template. Keep the contract "
        "and identity.py in sync."
    )


# ---------------------------------------------------------------------------
# 8. Contract self-consistency: the property enum, the predicate table, and the
#    property->type map are one 1:1 table. A drift within SKILL.md's own tables
#    (e.g. a property with no predicate, or a bogus type) fails here.
# ---------------------------------------------------------------------------


def test_contract_predicate_table_is_internally_consistent() -> None:
    # 7 properties, each with a distinct verb and a distinct object.
    assert len(CONTRACT_PREDICATE) == 7
    assert len(CONTRACT_TEMPLATE_VERBS) == 7, (
        "controlled verbs must be 1:1 with properties"
    )
    assert len(CONTRACT_PROPERTY_OBJECTS) == 7, (
        "property objects must be 1:1 with properties"
    )
    # every mapped type is a real claim type.
    mapped_types = {t for _v, _o, t in CONTRACT_PREDICATE.values()}
    assert mapped_types <= VALID_CLAIM_TYPES, (
        f"contract maps a property to an unknown claim type: {sorted(mapped_types - VALID_CLAIM_TYPES)}"
    )


# ---------------------------------------------------------------------------
# 9. The template is byte-canonical against normalize_text: a templated claim
#    normalizes to exactly [symbol, verb, object] -- nothing stripped, nothing
#    reordered, nothing added -- so two runs that reach the same cell hash to
#    the same id. Also proves backtick-robustness (a real variance source: one
#    run backticks the symbol, another doesn't; both must converge).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prop", sorted(CONTRACT_PREDICATE))
def test_template_is_byte_canonical_under_normalize(prop: str) -> None:
    verb, obj, _type = CONTRACT_PREDICATE[prop]
    sym = "alpha_sym"  # snake_case -> code span -> casefolds to itself
    bare = normalize_text(f"{sym} {verb} {obj}")
    assert bare == f"{sym} {verb} {obj}", (
        f"template for property {prop!r} did not normalize to itself: {bare!r}. "
        "A token was stripped/reordered -- the template is no longer byte-canonical."
    )
    backticked = normalize_text(f"`{sym}` {verb} {obj}")
    assert backticked == bare, (
        f"backticked vs bare symbol diverged for {prop!r}: {backticked!r} != {bare!r}. "
        "Whether the harvester backticks the symbol must not fork the claim_id."
    )


# ---------------------------------------------------------------------------
# 10. Distinctness across the enum (R-1 tie-in for the new vocab): on one fixed
#     symbol, the seven property predicates must produce seven DISTINCT
#     claim_ids -- no two properties collapse. (Each also carries its own type,
#     but the predicate text alone already separates them.)
# ---------------------------------------------------------------------------


def test_seven_properties_stay_distinct_on_one_symbol() -> None:
    sym = "max_delete"
    ids = {
        compute_claim_id(f"{sym} {verb} {obj}", claim_type, "docstring:mod.py")
        for verb, obj, claim_type in CONTRACT_PREDICATE.values()
    }
    assert len(ids) == len(CONTRACT_PREDICATE), (
        "two distinct property cells on the same symbol collapsed to one claim_id "
        "-- distinct claims would be silently merged (R-1)."
    )


# ---------------------------------------------------------------------------
# 11. Same predicate, different mechanism symbol -> distinct claim_ids. The
#     symbol is the template's only per-claim discriminator, so it MUST separate
#     two mechanisms that guard the same property.
# ---------------------------------------------------------------------------


def test_same_predicate_different_symbol_stays_distinct() -> None:
    verb, obj, claim_type = CONTRACT_PREDICATE["corruption"]
    id_a = compute_claim_id(f"alpha_sym {verb} {obj}", claim_type, "docstring:mod.py")
    id_b = compute_claim_id(f"beta_sym {verb} {obj}", claim_type, "docstring:mod.py")
    assert id_a != id_b, (
        "two different mechanisms guarding the same property collapsed to one "
        "claim_id -- the symbol failed to discriminate them."
    )


# ---------------------------------------------------------------------------
# 12. The full templated claim is idempotent under normalization (a claim
#     already in template form must be a fixed point).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sym", _SAMPLE_SYMBOLS)
def test_templated_claim_is_normalization_fixed_point(sym: str) -> None:
    verb, obj, _type = CONTRACT_PREDICATE["bound_quantity"]
    once = normalize_text(f"{sym} {verb} {obj}")
    twice = normalize_text(once)
    assert once == twice, (
        f"normalize_text is not idempotent on the templated claim for {sym!r}: "
        f"{once!r} -> {twice!r}."
    )
