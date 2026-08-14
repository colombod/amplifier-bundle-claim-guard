"""Stable claim identity (F-9).

claim_id = "clm_" + sha1(normalize(text) + "|" + type + "|" + repo_relpath_of(source))[:8]

Deliberately excludes `inferred`, `basis`, `quote`, line numbers, and the run -- a claim
keeps its identity across re-runs of an evolving PR, and across explicit<->implicit
reclassification. See docs/tool-claim-ledger-contract.md "Stable claim IDs across runs".

`normalize_text` (KI-1 hardening, design/ki1-determinism-spec.md §2): a claim's identity
must be reword-stable against trivial rewording (case, unicode, punctuation, articles,
contractions, identifier-case, text-embedded file:line drift) while never over-collapsing
two genuinely distinct claims into one id. Over-collapse is the #1 risk (spec R-1):
`ops.py::op_add_claim` treats an `identity_key` match as an idempotent re-add, so a false
merge silently drops a distinct claim and weakens the gate. Every choice below is biased
toward under-collapse (two claims stay distinct) over aggressive unification.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# ---------------------------------------------------------------------------
# §2.1 step 1 -- Unicode normalization + typographic quote folding.
#
# NFKC alone does not fold curly quotes to straight ASCII quotes (they are not
# canonically/compatibly equivalent in the Unicode Character Database). Since
# the design intent is that a smart-quote rendering of the same words must
# never fork identity -- and, more importantly, a curly apostrophe inside a
# contraction (e.g. "won\u2019t") must still be recognized by the contraction
# map below -- we fold the common typographic quote variants explicitly, in
# addition to NFKC.
# ---------------------------------------------------------------------------
_QUOTE_FOLD = str.maketrans(
    {
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u00a0": " ",  # non-breaking space
    }
)

# ---------------------------------------------------------------------------
# §2.2 -- Code-span detection: conservative, regex-based, longest-match-first.
#
# Bias conservative: when unsure, treat a token as code (preserve it), because
# preserving a token can only keep two claims distinct (safe direction), never
# merge them.
#
# Alternatives, in priority order:
#   1. backtick-delimited inline code
#   2. a file(.ext) token, optionally with a trailing :<line>
#   3. a snake_case identifier (contains '_')
#   4. a camelCase identifier (internal lowercase->uppercase transition)
#   5. a number, optionally signed / with a trailing unit
# ---------------------------------------------------------------------------
_CODE_SPAN = re.compile(
    r"`[^`]+`"
    r"|[\w./-]+\.[A-Za-z]{1,6}(?::\d+)?"
    r"|[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]*"
    r"|[a-z0-9]+[A-Z][A-Za-z0-9]*"
    r"|[-+]?\d[\d_]*[A-Za-z%]*"
)

# A file+line shape specifically, used to decide whether to strip a trailing
# ":<digits>" from a code span -- mirrors repo_relpath_of's line-drift rule,
# applied to a file:line token embedded in the claim *text* (not just `source`).
_CODE_SPAN_FILE_LINE = re.compile(r"^(.*\.[A-Za-z]{1,6}):\d+$")

# ---------------------------------------------------------------------------
# §2.1 step 3b -- Contraction expansion (meaning-preserving, closed, ordered).
#
# Specific forms are expanded first; a generic "strip n't, reattach not" rule
# would mangle "won't"/"can't" (giving "wo not"/"ca not"), so those need their
# own rules. The fallback covers any other "<stem>n't" contraction.
# `not` is never a filler -- expanding to "not" (never deleting it) is the point.
# ---------------------------------------------------------------------------
_CONTRACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bwon't\b"), "will not"),
    (re.compile(r"\bcan't\b"), "can not"),
    (re.compile(r"\bcannot\b"), "can not"),
    (re.compile(r"\bdon't\b"), "do not"),
    (re.compile(r"\bdoesn't\b"), "does not"),
    (re.compile(r"\bisn't\b"), "is not"),
    (re.compile(r"\baren't\b"), "are not"),
    (re.compile(r"\b(\w+)n't\b"), r"\1 not"),  # fallback: wasn't/weren't/hasn't/...
]

_APOSTROPHE_NO_SPACE = re.compile(r"(\w)'(\w)")
_NON_WORD = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")
_TRAILING_LINE_NUMBER = re.compile(r"^(.*):(\d+)$")

# ---------------------------------------------------------------------------
# §2.3 -- Filler phrases: multi-word claim boilerplate, removed as a
# phrase-level pre-pass (before tokenization), so "the code gates writes" and
# "gates writes" converge.
# ---------------------------------------------------------------------------
_FILLER_PHRASES = (
    "the code",
    "this change",
    "the system",
    "ensures that",
    "guarantees that",
    "such that",
)

# ---------------------------------------------------------------------------
# §2.3 -- Filler tokens: small, closed, hand-curated -- NOT a general English
# stopword list (which would strip meaning-bearing words and over-collapse).
#
# NOTE on "will": §2.3's prose enumerates `will` among the copula/aux fillers,
# but the spec's own worked example (§2.4 -- "A degraded server won't corrupt
# data." -> "degraded server will not corrupt data") asserts the new
# normalize_text output *retains* "will". Removing "will" as a filler would
# contradict that worked example (it would produce "degraded server not
# corrupt data" instead). Where the spec's prose enumeration and its worked
# example disagree, we resolve conservatively per R-1 (favor under-collapse,
# never over-collapse) and follow the worked example -- which is also what the
# unit tests below assert directly. `will` is therefore deliberately excluded
# from this set.
# ---------------------------------------------------------------------------
_FILLERS = frozenset(
    {"a", "an", "the", "is", "are", "be", "been", "would", "does", "do", "that"}
)

# ---------------------------------------------------------------------------
# §2.3 -- Never-strip guard: meaning-critical words that must never be treated
# as fillers, because stripping them is exactly what would merge a claim with
# its negation or its bound-inverted counterpart. Numbers are guarded
# structurally instead (they're captured as code spans and never tokenized as
# prose fillers at all), not via this set.
# ---------------------------------------------------------------------------
_NEVER_STRIP = frozenset(
    {
        "no",
        "not",
        "never",
        "none",
        "neither",
        "nor",
        "without",
        "can",
        "cannot",
        "must",
        "may",
        "should",
        "all",
        "every",
        "any",
        "each",
        "some",
        "only",
        "exactly",
        "most",
        "least",
        "at",
        "under",
        "over",
        "up",
        "to",
        "per",
    }
)

assert _FILLERS.isdisjoint(_NEVER_STRIP), (
    "a never-strip word must never be treated as a filler"
)


def _canonicalize_code_span(raw: str) -> str:
    """Casefold a code span while preserving its internal structure verbatim.

    Backticks are stripped. A detected `file.ext:line` token has its trailing
    line number stripped (line-drift stability), mirroring `repo_relpath_of`
    but applied to a file:line token embedded in the claim *text*.
    """
    inner = (
        raw[1:-1]
        if raw.startswith("`") and raw.endswith("`") and len(raw) >= 2
        else raw
    )
    inner = inner.casefold()
    match = _CODE_SPAN_FILE_LINE.match(inner)
    if match:
        return match.group(1)
    return inner


def _canonicalize_prose(text: str) -> str:
    """Aggressively canonicalize a prose span.

    casefold -> expand contractions -> delete no-space apostrophes -> fold all
    other punctuation to whitespace -> remove filler phrases -> tokenize and
    remove single-word fillers. Never touches negation, modals, quantifiers,
    or numbers (numbers never reach here -- they're code spans).
    """
    normalized = text.casefold()
    for pattern, replacement in _CONTRACTIONS:
        normalized = pattern.sub(replacement, normalized)
    normalized = _APOSTROPHE_NO_SPACE.sub(r"\1\2", normalized)
    normalized = _NON_WORD.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    for phrase in _FILLER_PHRASES:
        normalized = re.sub(rf"\b{re.escape(phrase)}\b", " ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    tokens = [tok for tok in normalized.split(" ") if tok and tok not in _FILLERS]
    return " ".join(tokens)


def normalize_text(text: str) -> str:
    """Canonicalize claim text for stable identity (F-9).

    Pipeline (design/ki1-determinism-spec.md §2.1):
    1. Unicode NFKC + typographic quote folding (whole string).
    2. Segment into code-spans (preserved atomically, casefolded, line-drift
       stable) and prose-spans (aggressively canonicalized: case, punctuation,
       contractions, closed-set fillers).
    3. Reassemble in original order, collapse whitespace, strip.

    Deliberately conservative -- explicitly NOT done, because each would risk
    merging distinct claims (over-collapse, spec R-1):
    - no token sorting / no bag-of-words (would merge subject/object swaps);
    - no stemming / no lemmatization / no singular<->plural folding (deferred
      to the prompt-level controlled vocabulary, spec §4, R-2);
    - no synonym mapping (meaning-adjacent words stay distinct at the hash).
    """
    folded = unicodedata.normalize("NFKC", text).translate(_QUOTE_FOLD)

    segments: list[str] = []
    cursor = 0
    for match in _CODE_SPAN.finditer(folded):
        prose = folded[cursor : match.start()]
        if prose:
            canon_prose = _canonicalize_prose(prose)
            if canon_prose:
                segments.append(canon_prose)
        segments.append(_canonicalize_code_span(match.group(0)))
        cursor = match.end()
    trailing_prose = folded[cursor:]
    if trailing_prose:
        canon_prose = _canonicalize_prose(trailing_prose)
        if canon_prose:
            segments.append(canon_prose)

    return _WHITESPACE.sub(" ", " ".join(segments)).strip()


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
