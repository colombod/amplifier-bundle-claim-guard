#!/usr/bin/env python3
"""Harvest-stability metric for KI-1 (design/ki1-determinism-spec.md section 6).

Measures whether the two harvester agents produce a *reproducible* claim set on the
same changeset -- the acceptance metric for KI-1. It does NOT run the harvesters
itself (that is an LLM step, run in a DTU per the never-install-locally rule); it
consumes the ledgers those runs produced and scores their agreement.

PRIMARY gate vs INDICATIVE diagnostics (KI-1 path (c) revision)
----------------------------------------------------------------
Empirically (N=5 repeat harvests on one fixed changeset, tightened prompt @2a97cb7),
exact claim_id identity across runs is NOT reproducible (mean pairwise Jaccard@claim_id
~0.0): free-form LLM harvest selects different symbols, at different granularity, on
every run, and semantic collapse is out of scope by design. Canonical phrasing (path a)
fixed HOW a claim is worded but not WHICH claims get selected -- so exact-id gating was
never a defensible bar for a free-form LLM harvest without a semantic-collapse step, and
temperature is inert as a lever on this model tier (Opus>=4.7).

What IS reproducible: the CATEGORY of concern a run surfaces (claim `type`, e.g.
`safety`/`integrity`/`performance`) is stable run-to-run (measured ~0.93), and the
predicate (verb+object, the claim minus its leading symbol) is moderately stable
(~0.55). This script therefore gates KI-1 on:

  * PRIMARY: `concern_type_overlap` (mean pairwise Jaccard over claim `type`) meeting
    `--min-concern-overlap`, AND the four incident blockers (B-1..B-4) caught every run.
  * INDICATIVE (reported, not gating by default): exact claim_id Jaccard, claim_id
    stability, predicate overlap, symbol overlap, and claim-count dispersion. These
    diagnose drift and regressions but free-form harvest is not expected to clear a
    high bar on them -- so they no longer fail the run by default.
  * `--strict-ids` re-enables the original exact-identity bar on demand (e.g. to prove
    a future semantic-collapse step actually converges the matrix), gating on
    `--min-jaccard`/`--min-id-stability` instead of concern-type overlap.

Because claim_id is computed by the SAME identity.py the ledger uses, this script also
detects prompt<->normalizer drift (spec risk R-6): if the agents drift from the canonical
form the normalizer expects, id-stability (still reported, indicative) drops here.

Usage
-----
    # Score N ledger.json files from N repeat harvest runs on ONE changeset
    # (PRIMARY gate: concern-type overlap + blockers; exact-id metrics are indicative):
    python scripts/harvest_stability.py run1/ledger.json run2/ledger.json ... \\
        [--min-concern-overlap 0.8] \\
        [--require-blocker B-1 --require-blocker B-2 ...] [--json]

    # Re-enable the original strict exact-claim_id bar on demand:
    python scripts/harvest_stability.py run1/ledger.json ... \\
        --strict-ids --min-jaccard 0.9 --min-id-stability 0.9

    # Self-check the metric on synthetic claim sets (no ledgers needed):
    python scripts/harvest_stability.py --selftest

Exit code: 0 if the active gate (primary, or strict-ids if given) + blocker guardrail
are met, 1 otherwise. Suitable for wiring into the acceptance methodology
(docs/EVALUATION.md).

A "claim" for scoring is identified by its claim_id. This script imports the REAL
identity.py so the metric matches ledger identity; if a ledger omits claim_id (older
format), it is recomputed from (text, type, source).
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path
from typing import Any

# Import the real identity module so scoring matches ledger identity exactly.
_MODULE_ROOT = Path(__file__).resolve().parent.parent / "modules" / "tool-claim-ledger"
if str(_MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODULE_ROOT))

try:
    from amplifier_module_tool_claim_ledger.identity import (  # type: ignore
        compute_claim_id,
    )
except ImportError:  # pragma: no cover - only when run outside the repo layout
    compute_claim_id = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Ledger parsing
# ---------------------------------------------------------------------------
def _claim_id_of(claim: dict[str, Any]) -> str | None:
    """The claim's stable id: prefer the stored one, else recompute from parts."""
    cid = claim.get("claim_id") or claim.get("id")
    if cid:
        return str(cid)
    if compute_claim_id is None:
        return None
    text = claim.get("text")
    ctype = claim.get("type") or claim.get("claim_type")
    source = claim.get("source")
    if text and ctype and source:
        return compute_claim_id(str(text), str(ctype), str(source))
    return None


def _iter_claims(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the list of claim dicts from a ledger, tolerant of shape."""
    claims = ledger.get("claims")
    if isinstance(claims, dict):
        return list(claims.values())
    if isinstance(claims, list):
        return claims
    return []


def load_claim_set(path: Path) -> tuple[set[str], list[dict[str, Any]]]:
    """Load a ledger.json; return (set of claim_ids, raw claim dicts)."""
    ledger = json.loads(path.read_text(encoding="utf-8"))
    claims = _iter_claims(ledger)
    ids: set[str] = set()
    for claim in claims:
        cid = _claim_id_of(claim)
        if cid:
            ids.add(cid)
    return ids, claims


# ---------------------------------------------------------------------------
# Exact-identity metrics (INDICATIVE -- see module docstring for why these are
# no longer the acceptance gate for free-form LLM harvest).
# ---------------------------------------------------------------------------
def jaccard(set_a: set[str], set_b: set[str]) -> float:
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 1.0


def mean_pairwise_jaccard(sets: list[set[str]]) -> float:
    pairs = list(itertools.combinations(range(len(sets)), 2))
    if not pairs:
        return 1.0
    return statistics.fmean(jaccard(sets[i], sets[j]) for i, j in pairs)


def id_stability(sets: list[set[str]]) -> float:
    """Share of (id, run) observations belonging to ids that appear in >=2 runs.

    High when the same claim_ids recur across runs (the code fix working); low when
    every run invents fresh ids (the pre-fix failure). 1.0 for a single run.
    """
    if len(sets) < 2:
        return 1.0
    counts: dict[str, int] = {}
    for s in sets:
        for cid in s:
            counts[cid] = counts.get(cid, 0) + 1
    total_obs = sum(counts.values())
    recurring_obs = sum(n for n in counts.values() if n >= 2)
    return recurring_obs / total_obs if total_obs else 1.0


def count_dispersion(sets: list[set[str]]) -> dict[str, float]:
    counts = [len(s) for s in sets]
    if not counts:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "stdev": 0.0}
    return {
        "min": float(min(counts)),
        "max": float(max(counts)),
        "mean": statistics.fmean(counts),
        "stdev": statistics.pstdev(counts) if len(counts) > 1 else 0.0,
    }


# ---------------------------------------------------------------------------
# Coarse-key metrics (PRIMARY / supporting) -- what actually recurs run-to-run
# for a free-form LLM harvest: the CATEGORY of concern, and (moderately) the
# predicate. Each is mean pairwise Jaccard over a coarser key than claim_id.
# ---------------------------------------------------------------------------
def _type_of(claim: dict[str, Any]) -> str | None:
    """Coarsest key: the claim's concern category (e.g. safety/integrity/performance)."""
    ctype = claim.get("type") or claim.get("claim_type")
    if not ctype:
        return None
    return str(ctype).strip().lower()


def _symbol_of(claim: dict[str, Any]) -> str | None:
    """Leading whitespace-delimited token of `text` -- the symbol a claim is about."""
    text = claim.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip().split(maxsplit=1)[0].lower()


def _predicate_of(claim: dict[str, Any]) -> str | None:
    """`text` with its leading symbol removed -- the verb+object predicate."""
    text = claim.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip().lower()


def _key_sets(raw: list[list[dict[str, Any]]], key_fn: Any) -> list[set[str]]:
    """Build one coarse-key set per run, skipping claims missing that field."""
    sets: list[set[str]] = []
    for claims in raw:
        keys = {key_fn(c) for c in claims}
        keys.discard(None)
        sets.append(keys)
    return sets


def concern_type_overlap(raw: list[list[dict[str, Any]]]) -> float:
    """Mean pairwise Jaccard over claim `type` -- PRIMARY gate metric.

    Measures whether the same CATEGORIES of concern (safety, integrity,
    performance, ...) surface every run, independent of exact wording or
    which specific symbol/claim was selected.
    """
    return mean_pairwise_jaccard(_key_sets(raw, _type_of))


def predicate_overlap(raw: list[list[dict[str, Any]]]) -> float:
    """Mean pairwise Jaccard over the verb+object predicate (indicative)."""
    return mean_pairwise_jaccard(_key_sets(raw, _predicate_of))


def symbol_overlap(raw: list[list[dict[str, Any]]]) -> float:
    """Mean pairwise Jaccard over the leading symbol token (indicative)."""
    return mean_pairwise_jaccard(_key_sets(raw, _symbol_of))


def blockers_caught_every_run(
    ledgers: list[list[dict[str, Any]]], required: list[str]
) -> dict[str, bool]:
    """For each required blocker tag, is it present in EVERY run's claim set?

    Conservative substring match over a claim's tag/label/text fields.
    """
    result: dict[str, bool] = {}
    for tag in required:
        needle = tag.lower()
        present_each: list[bool] = []
        for claims in ledgers:
            found = any(
                needle
                in " ".join(
                    str(c.get(k, ""))
                    for k in ("blocker", "tags", "label", "text", "note")
                ).lower()
                for c in claims
            )
            present_each.append(found)
        result[tag] = bool(present_each) and all(present_each)
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def _score_core(
    sets: list[set[str]],
    raw: list[list[dict[str, Any]]],
    min_jaccard: float,
    min_id_stability: float,
    required_blockers: list[str],
    min_concern_overlap: float,
    strict_ids: bool,
) -> dict[str, Any]:
    mj = mean_pairwise_jaccard(sets)
    ids_stab = id_stability(sets)
    disp = count_dispersion(sets)
    blockers = (
        blockers_caught_every_run(raw, required_blockers) if required_blockers else {}
    )
    blockers_ok = all(blockers.values()) if blockers else True

    concern_overlap = concern_type_overlap(raw)
    pred_overlap = predicate_overlap(raw)
    sym_overlap = symbol_overlap(raw)

    concern_ok = concern_overlap >= min_concern_overlap
    jaccard_ok = mj >= min_jaccard
    id_ok = ids_stab >= min_id_stability

    if strict_ids:
        passed = jaccard_ok and id_ok and blockers_ok
    else:
        passed = concern_ok and blockers_ok

    return {
        "runs": len(sets),
        "primary_gate": {
            "concern_type_overlap": round(concern_overlap, 4),
            "min_concern_overlap": min_concern_overlap,
            "concern_overlap_ok": concern_ok,
            "blockers_caught_every_run": blockers,
            "blockers_ok": blockers_ok,
        },
        "indicative": {
            "note": (
                "Exact claim_id reproducibility is intentionally NOT the acceptance "
                "bar: free-form LLM harvest + no semantic-collapse step by design, and "
                "temperature is inert on Opus>=4.7. Reported as diagnostics only."
            ),
            "mean_pairwise_jaccard_claim_id": round(mj, 4),
            "id_stability": round(ids_stab, 4),
            "predicate_overlap": round(pred_overlap, 4),
            "symbol_overlap": round(sym_overlap, 4),
            "count_dispersion": {k: round(v, 3) for k, v in disp.items()},
            "min_jaccard": min_jaccard,
            "min_id_stability": min_id_stability,
            "jaccard_ok": jaccard_ok,
            "id_stability_ok": id_ok,
        },
        "strict_ids": {
            "enabled": strict_ids,
            "min_jaccard": min_jaccard,
            "min_id_stability": min_id_stability,
        },
        "passed": passed,
    }


def score(
    ledger_paths: list[Path],
    min_jaccard: float = 0.0,
    min_id_stability: float = 0.0,
    required_blockers: list[str] | None = None,
    min_concern_overlap: float = 0.8,
    strict_ids: bool = False,
) -> dict[str, Any]:
    required_blockers = required_blockers or []
    sets: list[set[str]] = []
    raw: list[list[dict[str, Any]]] = []
    for path in ledger_paths:
        ids, claims = load_claim_set(path)
        sets.append(ids)
        raw.append(claims)

    return _score_core(
        sets,
        raw,
        min_jaccard,
        min_id_stability,
        required_blockers,
        min_concern_overlap,
        strict_ids,
    )


def _print_human(report: dict[str, Any]) -> None:
    print(f"Harvest-stability over {report['runs']} run(s):")
    print()

    pg = report["primary_gate"]
    print("PRIMARY GATE (what KI-1 is actually scored on):")
    print(
        f"  concern-type overlap (Jaccard@type)    : {pg['concern_type_overlap']} "
        f"(>= {pg['min_concern_overlap']}? "
        f"{'PASS' if pg['concern_overlap_ok'] else 'FAIL'})"
    )
    if pg["blockers_caught_every_run"]:
        print("  blockers caught every run:")
        for tag, ok in pg["blockers_caught_every_run"].items():
            print(f"    {tag}: {'PASS' if ok else 'FAIL'}")

    print()
    ind = report["indicative"]
    print("INDICATIVE DIAGNOSTICS (reported, NOT gating unless --strict-ids):")
    print(f"  note: {ind['note']}")
    print(
        f"  mean pairwise Jaccard@claim_id (exact)  : {ind['mean_pairwise_jaccard_claim_id']} "
        f"(indicative; ref threshold {ind['min_jaccard']})"
    )
    print(
        f"  claim_id stability                      : {ind['id_stability']} "
        f"(indicative; ref threshold {ind['min_id_stability']})"
    )
    print(f"  predicate overlap (verb+object)          : {ind['predicate_overlap']}")
    print(f"  symbol overlap (leading token)           : {ind['symbol_overlap']}")
    disp = ind["count_dispersion"]
    print(
        f"  claim count per run                      : min={disp['min']} max={disp['max']} "
        f"mean={disp['mean']} stdev={disp['stdev']}"
    )

    strict = report["strict_ids"]
    if strict["enabled"]:
        print()
        print(
            f"  --strict-ids ON: gating on exact Jaccard >= {strict['min_jaccard']} "
            f"and id-stability >= {strict['min_id_stability']} instead of "
            "concern-type overlap"
        )

    print()
    print(f"  VERDICT: {'PASS' if report['passed'] else 'FAIL'}")


# ---------------------------------------------------------------------------
# Self-test (no ledgers required) -- proves the metric behaves as intended.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    ok = True

    identical = [{"a", "b", "c"}, {"a", "b", "c"}, {"a", "b", "c"}]
    disjoint = [{"a", "b"}, {"c", "d"}, {"e", "f"}]

    if mean_pairwise_jaccard(identical) != 1.0:
        print("FAIL: identical sets should have Jaccard 1.0")
        ok = False
    if mean_pairwise_jaccard(disjoint) != 0.0:
        print("FAIL: disjoint sets should have Jaccard 0.0")
        ok = False
    if id_stability(identical) != 1.0:
        print("FAIL: identical sets should have id_stability 1.0")
        ok = False
    if id_stability(disjoint) != 0.0:
        print("FAIL: disjoint sets should have id_stability 0.0")
        ok = False

    # Partial overlap: 2 shared of 4 union -> Jaccard 1/3 pairwise.
    partial = [{"a", "b", "c"}, {"a", "b", "d"}]
    if abs(mean_pairwise_jaccard(partial) - 0.5) > 1e-9:
        print(f"FAIL: expected Jaccard 0.5, got {mean_pairwise_jaccard(partial)}")
        ok = False

    # Blocker guardrail: present in every run vs missing from one.
    every = [[{"text": "B-1 leak"}], [{"label": "b-1"}]]
    missing = [[{"text": "B-1 leak"}], [{"text": "unrelated"}]]
    if not blockers_caught_every_run(every, ["B-1"])["B-1"]:
        print("FAIL: B-1 present in all runs should pass")
        ok = False
    if blockers_caught_every_run(missing, ["B-1"])["B-1"]:
        print("FAIL: B-1 missing from a run should fail")
        ok = False

    # --- Coarse concern-overlap metrics (KI-1 path c) ---------------------
    # Two runs: different symbols and different claim_ids every time (the
    # measured real-world failure mode), but the same CATEGORIES of concern
    # (safety, integrity) surface both times.
    run_a = [
        {"claim_id": "id1", "text": "SymbolA preserves invariant", "type": "safety"},
        {"claim_id": "id2", "text": "SymbolB rejects bad input", "type": "integrity"},
    ]
    run_b = [
        {"claim_id": "id3", "text": "SymbolC preserves invariant", "type": "safety"},
        {"claim_id": "id4", "text": "SymbolD rejects bad input", "type": "integrity"},
    ]
    raw_matching_types = [run_a, run_b]
    id_sets_matching = [
        {c["claim_id"] for c in run_a},
        {c["claim_id"] for c in run_b},
    ]

    ct_overlap = concern_type_overlap(raw_matching_types)
    if abs(ct_overlap - 1.0) > 1e-9:
        print(f"FAIL: expected concern_type_overlap 1.0, got {ct_overlap}")
        ok = False
    if mean_pairwise_jaccard(id_sets_matching) != 0.0:
        print("FAIL: expected exact claim_id Jaccard 0.0 for disjoint synthetic ids")
        ok = False

    report_matching = _score_core(
        id_sets_matching,
        raw_matching_types,
        min_jaccard=0.0,
        min_id_stability=0.0,
        required_blockers=[],
        min_concern_overlap=0.8,
        strict_ids=False,
    )
    if not report_matching["passed"]:
        print(
            "FAIL: expected passed=True at default gate when concern types fully "
            "overlap despite exact-id 0.0"
        )
        ok = False
    if report_matching["primary_gate"]["concern_type_overlap"] != 1.0:
        print("FAIL: report concern_type_overlap should be 1.0")
        ok = False
    if report_matching["indicative"]["mean_pairwise_jaccard_claim_id"] != 0.0:
        print("FAIL: report exact jaccard should be 0.0 (indicative, non-gating)")
        ok = False

    # Differing concern types across runs -> overlap well below the default
    # threshold -> primary gate should fail.
    run_c = [
        {
            "claim_id": "id5",
            "text": "SymbolE degrades gracefully",
            "type": "performance",
        }
    ]
    raw_diff_types = [run_a, run_c]
    id_sets_diff = [
        {c["claim_id"] for c in run_a},
        {c["claim_id"] for c in run_c},
    ]
    ct_overlap_diff = concern_type_overlap(raw_diff_types)
    if ct_overlap_diff >= 1.0:
        print(
            f"FAIL: expected concern_type_overlap < 1.0 for differing types, "
            f"got {ct_overlap_diff}"
        )
        ok = False

    report_diff = _score_core(
        id_sets_diff,
        raw_diff_types,
        min_jaccard=0.0,
        min_id_stability=0.0,
        required_blockers=[],
        min_concern_overlap=0.8,
        strict_ids=False,
    )
    if report_diff["passed"]:
        print(
            "FAIL: expected passed=False when concern-type overlap is below "
            "--min-concern-overlap"
        )
        ok = False

    # --strict-ids re-enables the original exact-identity bar on demand.
    report_strict = _score_core(
        id_sets_matching,
        raw_matching_types,
        min_jaccard=0.9,
        min_id_stability=0.9,
        required_blockers=[],
        min_concern_overlap=0.8,
        strict_ids=True,
    )
    if report_strict["passed"]:
        print(
            "FAIL: expected passed=False under --strict-ids when exact ids are "
            "disjoint (0.0 Jaccard against a 0.9 bar)"
        )
        ok = False

    print("selftest: PASS" if ok else "selftest: FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "ledgers", nargs="*", type=Path, help="ledger.json files, one per run"
    )
    parser.add_argument(
        "--min-concern-overlap",
        type=float,
        default=0.8,
        help=(
            "PRIMARY gate: min mean pairwise Jaccard over claim `type` (concern "
            "category) across runs (default: 0.8)"
        ),
    )
    parser.add_argument(
        "--min-jaccard",
        type=float,
        default=0.0,
        help=(
            "indicative only (default: 0.0, non-gating) unless --strict-ids is set, "
            "in which case this becomes a gating threshold on exact claim_id Jaccard"
        ),
    )
    parser.add_argument(
        "--min-id-stability",
        type=float,
        default=0.0,
        help=(
            "indicative only (default: 0.0, non-gating) unless --strict-ids is set, "
            "in which case this becomes a gating threshold on exact claim_id stability"
        ),
    )
    parser.add_argument(
        "--strict-ids",
        action="store_true",
        help=(
            "re-enable the original strict bar: gate on exact claim_id Jaccard "
            "(--min-jaccard) and id-stability (--min-id-stability) instead of "
            "concern-type overlap. Use to prove a future semantic-collapse step "
            "actually converges the exact matrix."
        ),
    )
    parser.add_argument(
        "--require-blocker",
        action="append",
        default=[],
        metavar="TAG",
        help="a blocker tag that must appear in every run (repeatable), e.g. B-1",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument(
        "--selftest", action="store_true", help="run the metric self-check and exit"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if len(args.ledgers) < 2:
        parser.error(
            "need at least 2 ledger.json files to measure run-to-run stability"
        )

    report = score(
        args.ledgers,
        min_jaccard=args.min_jaccard,
        min_id_stability=args.min_id_stability,
        required_blockers=args.require_blocker,
        min_concern_overlap=args.min_concern_overlap,
        strict_ids=args.strict_ids,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
