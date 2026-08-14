#!/usr/bin/env python3
"""Harvest-stability metric for KI-1 (design/ki1-determinism-spec.md section 6).

Measures whether the two harvester agents produce a *reproducible* claim set on the
same changeset -- the acceptance metric for KI-1. It does NOT run the harvesters
itself (that is an LLM step, run in a DTU per the never-install-locally rule); it
consumes the ledgers those runs produced and scores their agreement.

Two levels of read, by design:
  * claim_id STABILITY isolates the code-level fix (identity.py normalization): of the
    claim observations across runs, what share belong to ids that recur across runs?
  * Jaccard@claim_id isolates the prompt-level fix (granularity + canonical phrasing):
    how much do the claim SETS overlap run-to-run?
Plus a hard guardrail: the four incident blockers (B-1..B-4) must be caught every run.

Because claim_id is computed by the SAME identity.py the ledger uses, this script also
detects prompt<->normalizer drift (spec risk R-6): if the agents drift from the canonical
form the normalizer expects, id-stability drops here.

Usage
-----
    # Score N ledger.json files from N repeat harvest runs on ONE changeset:
    python scripts/harvest_stability.py run1/ledger.json run2/ledger.json ... \
        [--min-jaccard 0.9] [--min-id-stability 0.9] \
        [--require-blocker B-1 --require-blocker B-2 ...] [--json]

    # Self-check the metric on synthetic claim sets (no ledgers needed):
    python scripts/harvest_stability.py --selftest

Exit code: 0 if every threshold + blocker guardrail is met, 1 otherwise. Suitable for
wiring into the acceptance methodology (docs/EVALUATION.md).

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
# Metrics
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
def score(
    ledger_paths: list[Path],
    min_jaccard: float,
    min_id_stability: float,
    required_blockers: list[str],
) -> dict[str, Any]:
    sets: list[set[str]] = []
    raw: list[list[dict[str, Any]]] = []
    for path in ledger_paths:
        ids, claims = load_claim_set(path)
        sets.append(ids)
        raw.append(claims)

    mj = mean_pairwise_jaccard(sets)
    ids_stab = id_stability(sets)
    disp = count_dispersion(sets)
    blockers = (
        blockers_caught_every_run(raw, required_blockers) if required_blockers else {}
    )

    jaccard_ok = mj >= min_jaccard
    id_ok = ids_stab >= min_id_stability
    blockers_ok = all(blockers.values()) if blockers else True
    passed = jaccard_ok and id_ok and blockers_ok

    return {
        "runs": len(sets),
        "mean_pairwise_jaccard": round(mj, 4),
        "id_stability": round(ids_stab, 4),
        "count_dispersion": {k: round(v, 3) for k, v in disp.items()},
        "blockers_caught_every_run": blockers,
        "thresholds": {
            "min_jaccard": min_jaccard,
            "min_id_stability": min_id_stability,
        },
        "checks": {
            "jaccard_ok": jaccard_ok,
            "id_stability_ok": id_ok,
            "blockers_ok": blockers_ok,
        },
        "passed": passed,
    }


def _print_human(report: dict[str, Any]) -> None:
    print(f"Harvest-stability over {report['runs']} run(s):")
    print(
        f"  mean pairwise Jaccard@claim_id : {report['mean_pairwise_jaccard']} "
        f"(>= {report['thresholds']['min_jaccard']}? "
        f"{'PASS' if report['checks']['jaccard_ok'] else 'FAIL'})"
    )
    print(
        f"  claim_id stability             : {report['id_stability']} "
        f"(>= {report['thresholds']['min_id_stability']}? "
        f"{'PASS' if report['checks']['id_stability_ok'] else 'FAIL'})"
    )
    disp = report["count_dispersion"]
    print(
        f"  claim count per run            : min={disp['min']} max={disp['max']} "
        f"mean={disp['mean']} stdev={disp['stdev']}"
    )
    if report["blockers_caught_every_run"]:
        print("  blockers caught every run:")
        for tag, ok in report["blockers_caught_every_run"].items():
            print(f"    {tag}: {'PASS' if ok else 'FAIL'}")
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

    print("selftest: PASS" if ok else "selftest: FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ledgers", nargs="*", type=Path, help="ledger.json files, one per run"
    )
    parser.add_argument("--min-jaccard", type=float, default=0.9)
    parser.add_argument("--min-id-stability", type=float, default=0.9)
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
        args.ledgers, args.min_jaccard, args.min_id_stability, args.require_blocker
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
