"""The `claim_ledger` tool -- a single tool dispatched by an `operation` parameter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from amplifier_core import ToolResult

from .ops import HANDLERS
from .store import LedgerStore, WriteConfinementError

_OPERATIONS = sorted(HANDLERS.keys())


class ClaimLedgerTool:
    """Deterministic claim ledger for the claim-guard adversarial claim-verification gate.

    Dispatches on `operation`. Persists to <repo_root>/<run_dir>/<run_id>/ledger.json.
    Never writes elsewhere.

    `repo_root` is resolved ONCE, at construction time (i.e. once per mount / per
    session) -- not re-derived from `Path.cwd()` on every call. Real runs often
    execute from an ephemeral or container cwd (DTU, /tmp); re-deriving `Path.cwd()`
    on every `execute()` call means the only durable artifact of a run -- including a
    BLOCK verdict -- can die with that cwd, and cross-call cwd drift can split one
    run across two different confinement roots. Resolving once and holding it on the
    instance eliminates both failure modes for the lifetime of this tool instance.

    `repo_root` is overridable via config (same pattern as `run_dir`) so a run
    executing inside a container can be pointed at a stable mounted path instead of
    the container's (ephemeral) cwd. Defaults to `Path.cwd()` at construction time
    when not configured.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.run_dir = config.get("run_dir", ".claim-guard")
        repo_root_override = config.get("repo_root")
        self.repo_root: Path = (
            Path(repo_root_override).expanduser().resolve()
            if repo_root_override
            else Path.cwd()
        )

    @property
    def name(self) -> str:
        return "claim_ledger"

    @property
    def description(self) -> str:
        return (
            "Deterministic claim ledger for the adversarial claim-verification gate. "
            "Dispatched by `operation`: add_claim, list_claims, record_verdict, "
            "record_lens_error, declare_roster, record_debate, waive, record_probe, "
            "defer_claim, graduate_test, aggregate, gate, render_matrix, start_run, "
            "add_claims, report, list_runs. Persists to "
            "<repo_root>/<run_dir>/<run_id>/ledger.json -- the only write capability "
            "in the gate session, written atomically (temp file + fsync + os.replace) "
            "so a crash mid-write can never corrupt or truncate a run's only durable "
            "record. `repo_root` is resolved ONCE at construction (config-overridable), "
            "never re-derived from cwd per call, and every run's resolved "
            "`ledger_root`/`ledger_path` is persisted into the run record itself and "
            "returned by start_run/gate/report -- so a BLOCK verdict is never "
            "presented without also saying where its only durable record lives. "
            "Computes worst-wins aggregation and the gate verdict as pure, "
            "deterministic functions -- never via LLM judgment -- and structurally "
            "enforces file:line evidence anchors and an evidence ratchet so a "
            "REFUTED verdict cannot be talked away without new evidence. Phase-2 "
            "probing coverage (record_probe/defer_claim/graduate_test) is honest: "
            "only graduate_test (full criteria met) or record_verdict's "
            "adverse_state_test clear gate limb 2 for a safety claim -- a "
            "SURVIVED-but-ungraduated probe or a deferred claim still blocks. "
            "record_lens_error makes a crashed lens observable to gate limb 4 "
            "(distinct from a merely-PENDING claim) without ever fabricating a "
            "verdict. declare_roster records the run's expected-lens POLICY once; "
            "the ledger derives, per claim, exactly which lenses are expected (from "
            "claim.type + the policy) and the gate reports any rostered lens that "
            "left no trace as lens-coverage-gap, any off-roster verdict as "
            "roster-inconsistency, and any run that never declared a roster as "
            "no-roster-declared -- all three INDETERMINATE, never a rejected "
            "verdict. `probe_scope` (set on start_run, default 'in-scope') governs "
            "whether gate limb 2 BLOCKs ('in-scope') or is merely surfaced as an "
            "advisory reason on `advisory_reasons` ('out-of-scope', for a "
            "static-only run that never had the mandate to gather dynamic "
            "adverse-state evidence) -- either way it never fabricates a verdict "
            "for claims outside its scope. start_run/add_claims/report are thin "
            "conveniences over the same handlers -- they never bypass validation: "
            "start_run explicitly creates a run without adding a claim first; "
            "add_claims bulk-adds a `claims` array in one call (isolating "
            "per-element failures in `errors` without dropping the rest of the "
            "batch); report returns gate + render_matrix's combined output in one "
            "round trip. list_runs is read-only and takes no run_id: it enumerates "
            "every run under the confinement root and flags STRANDED runs -- ones "
            "with claims but at least one still PENDING (no verdict), i.e. "
            "harvested-but-unverdicted -- so an abandoned run is a queryable state "
            "rather than a silent drop; pass stranded_only to filter to just those "
            "runs."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": _OPERATIONS,
                    "description": "Which ledger operation to perform.",
                },
                "run_id": {
                    "type": "string",
                    "description": (
                        "Run identifier. Required for every operation except "
                        "start_run, including add_claim and add_claims -- obtain one "
                        "from start_run first. An empty/omitted run_id on add_claim/"
                        "add_claims is rejected (invalid_input); a non-empty run_id "
                        "with no existing run is rejected (run_not_found) -- neither "
                        "is ever silently forked into a new run. start_run's own "
                        "run_id is OPTIONAL: omitted mints a fresh id; a caller-"
                        "supplied id resumes that run if it already exists (claims/"
                        "policy/roster untouched) or creates a new run at that id "
                        "if it does not; an invalid id is rejected as "
                        "write_confinement_violation."
                    ),
                },
                "claim_id": {
                    "type": "string",
                    "description": "Stable claim identifier (clm_...).",
                },
                "text": {"type": "string", "description": "add_claim: the claim text."},
                "type": {
                    "type": "string",
                    "enum": [
                        "correspondence",
                        "safety",
                        "quantitative",
                        "temporal",
                        "concurrency",
                        "coverage",
                    ],
                    "description": "add_claim: claim type.",
                },
                "source": {
                    "type": "string",
                    "description": "add_claim: where the claim came from.",
                },
                "inferred": {
                    "type": "boolean",
                    "description": "add_claim: true for implicit claims.",
                },
                "basis": {
                    "type": "string",
                    "description": "add_claim: one-line derivation (implicit claims).",
                },
                "quote": {
                    "type": "string",
                    "description": "add_claim: verbatim source line (explicit claims).",
                },
                "lens": {
                    "type": "string",
                    "description": (
                        "record_verdict: the lens recording this verdict. "
                        "record_lens_error: the lens that errored."
                    ),
                },
                "error": {
                    "type": "string",
                    "description": (
                        "record_lens_error: the error/crash message. Never creates a "
                        "verdict or touches aggregate/adverse_state_test -- it only "
                        "surfaces gate limb 4 as a distinct lens-error:<lens>@<claim_id> "
                        "reason."
                    ),
                },
                "verdict": {
                    "type": "string",
                    "enum": ["CONFIRMED", "REFUTED", "UNTESTABLE", "N/A"],
                    "description": "record_verdict: the verdict being recorded.",
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "record_verdict: file:line anchors (required for CONFIRMED/REFUTED).",
                },
                "counter_case": {
                    "type": "string",
                    "description": "record_verdict: required for REFUTED -- the input/state/sequence that breaks the claim.",
                },
                "adverse_state_test": {
                    "type": "object",
                    "description": "record_verdict: optional update to the claim's adverse_state_test.",
                },
                "round": {
                    "type": "integer",
                    "description": "record_verdict/record_debate: debate round number.",
                },
                "to_lens": {
                    "type": "string",
                    "description": "record_debate: which lens received the relay.",
                },
                "relayed_payload": {
                    "description": "record_debate: the verbatim payload relayed."
                },
                "from_lenses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "record_debate: which lenses' findings were relayed.",
                },
                "by": {"type": "string", "description": "waive: who is waiving."},
                "reason": {
                    "type": "string",
                    "description": "waive: why. defer_claim: why the probe was deferred.",
                },
                "probe": {
                    "type": "object",
                    "description": (
                        "record_probe: { designed_by, adverse_state, outcome: "
                        "FALSIFIED|SURVIVED|UNBUILDABLE, evidence?, artifacts_path? }. "
                        "Never itself sets adverse_state_test."
                    ),
                },
                "standing_test": {
                    "type": "object",
                    "description": (
                        "graduate_test: { path, asserts_property, red_before, "
                        "green_after, deterministic_runs }. Rejected unless all of "
                        "asserts_property/red_before/green_after are true and "
                        "deterministic_runs >= 3."
                    ),
                },
                "gate_policy": {
                    "type": "string",
                    "enum": ["advisory", "blocking-with-waiver", "blocking"],
                    "description": "gate: policy override (defaults to the run's stored policy).",
                },
                "probe_scope": {
                    "type": "string",
                    "enum": ["in-scope", "out-of-scope"],
                    "description": (
                        "start_run: whether dynamic probing is in scope for this "
                        "run (default 'in-scope'). 'out-of-scope' (a static-only "
                        "run, e.g. the verify-claims MVP) downgrades gate limb 2 "
                        "(safety claim with no adverse-state test) from a BLOCK "
                        "to an advisory reason -- see gate's advisory_reasons."
                    ),
                },
                "mandatory": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "declare_roster: lens names expected on EVERY claim regardless "
                        "of type. MAY be empty (the explicit opt-out -- see conditional)."
                    ),
                },
                "conditional": {
                    "type": "object",
                    "description": (
                        "declare_roster: { <lens>: { types: [claim_type,...], "
                        "included: bool, reason: str } }. `included` and `reason` "
                        "are both required whether including or excluding a lens -- "
                        "exclusion is an auditable decision, not a silent drop."
                    ),
                },
                "declared_by": {
                    "type": "string",
                    "description": "declare_roster: free-form provenance (optional).",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "description": "render_matrix/report: output format.",
                },
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "correspondence",
                                    "safety",
                                    "quantitative",
                                    "temporal",
                                    "concurrency",
                                    "coverage",
                                ],
                            },
                            "source": {"type": "string"},
                            "inferred": {"type": "boolean"},
                            "basis": {"type": "string"},
                            "quote": {"type": "string"},
                        },
                        "required": ["text", "type", "source"],
                    },
                    "description": (
                        "add_claims: batch of claims to add, each shaped like "
                        "add_claim's own fields. A malformed element is isolated in "
                        "the result's `errors` array and does not abort the batch."
                    ),
                },
                "stranded_only": {
                    "type": "boolean",
                    "description": (
                        "list_runs: if true, only return runs that are STRANDED -- "
                        "have at least one claim and at least one of those claims "
                        "still PENDING (no verdict recorded). `stranded_count` in "
                        "the result always reflects the true total across ALL runs "
                        "regardless of this filter."
                    ),
                },
            },
            "required": ["operation"],
        }

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        operation = input_data.get("operation")
        handler = HANDLERS.get(operation) if isinstance(operation, str) else None
        if handler is None:
            return ToolResult(
                success=False,
                output={
                    "ok": False,
                    "error": "unknown_operation",
                    "message": f"Unknown operation {operation!r}. Valid operations: {_OPERATIONS}",
                },
            )

        store = LedgerStore(repo_root=self.repo_root, run_dir=self.run_dir)
        try:
            result = handler(store, input_data)
        except WriteConfinementError as exc:
            return ToolResult(
                success=False,
                output={
                    "ok": False,
                    "error": "write_confinement_violation",
                    "message": str(exc),
                },
            )

        return ToolResult(success=bool(result.get("ok", True)), output=result)
