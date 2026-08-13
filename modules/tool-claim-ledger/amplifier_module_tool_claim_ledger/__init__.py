"""Amplifier tool module: claim-ledger.

The deterministic trust anchor of the claim-guard bundle. See
docs/tool-claim-ledger-contract.md at the bundle root for the authoritative
interface contract.
"""

from __future__ import annotations

import logging
from typing import Any

from .tool import ClaimLedgerTool

logger = logging.getLogger(__name__)

__all__ = ["ClaimLedgerTool", "mount"]


async def mount(
    coordinator: Any, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Mount the `claim_ledger` tool into the coordinator."""
    tool = ClaimLedgerTool(config=config or {})
    await coordinator.mount("tools", tool, name=tool.name)
    logger.info("tool-claim-ledger mounted: registered 'claim_ledger'")
    return {
        "name": "tool-claim-ledger",
        "version": "0.1.0",
        "provides": ["claim_ledger"],
    }
