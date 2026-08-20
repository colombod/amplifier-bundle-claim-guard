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

    Dispatches on `operation`. Persists to <repo>/<run_dir>/<run_id>/ledger.json where
    <repo> is the tool's working directory at execute time. Never writes elsewhere.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.run_dir = config.get("run_dir", ".claim-guard")

    @property
    def name(self) -> str:
        return "claim_ledger"

    @property
    def description(self) -> str:
        return (
            "Deterministic claim ledger for the adversarial claim-verification gate. "
            "Dispatched by `operation`: add_claim, list_claims, record_verdict, "
            "record_lens_error, record_debate, waive, record_probe, defer_claim, "
            "graduate_test, aggregate, gate, render_matrix, start_run, add_claims, "
            "report. Persists to <repo>/<run_dir>/<run_id>/ledger.json -- the only "
            "write capability in the gate session. Computes worst-wins aggregation "
            "and the gate verdict as pure, deterministic functions -- never via LLM "
            "judgment -- and structurally enforces file:line evidence anchors and an "
            "evidence ratchet so a REFUTED verdict cannot be talked away without new "
            "evidence. Phase-2 probing coverage (record_probe/defer_claim/"
            "graduate_test) is honest: only graduate_test (full criteria met) or "
            "record_verdict's adverse_state_test clear gate limb 2 for a safety "
            "claim -- a SURVIVED-but-ungraduated probe or a deferred claim still "
            "blocks. record_lens_error makes a crashed lens observable to gate limb 4 "
            "(distinct from a merely-PENDING claim) without ever fabricating a "
            "verdict. start_run/add_claims/report are thin conveniences over the "
            "same handlers -- they never bypass validation: start_run explicitly "
            "creates a run without adding a claim first; add_claims bulk-adds a "
            "`claims` array in one call (isolating per-element failures in `errors` "
            "without dropping the rest of the batch); report returns gate + "
            "render_matrix's combined output in one round trip."
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
                        "Run identifier. If empty on the first add_claim, one is derived "
                        "and returned. Required for all other operations."
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

        store = LedgerStore(repo_root=Path.cwd(), run_dir=self.run_dir)
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
