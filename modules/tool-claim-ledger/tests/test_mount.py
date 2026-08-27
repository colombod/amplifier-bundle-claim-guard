"""Protocol compliance: mount() must register a real tool via coordinator.mount()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from amplifier_module_tool_claim_ledger import mount


@pytest.mark.asyncio
async def test_mount_registers_tool() -> None:
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    result = await mount(coordinator)

    coordinator.mount.assert_called_once()
    call_args = coordinator.mount.call_args
    assert call_args[0][0] == "tools"
    assert call_args[1]["name"] == "claim_ledger"

    assert result is not None
    assert result["name"] == "tool-claim-ledger"
    assert "provides" in result
    assert "claim_ledger" in result["provides"]


@pytest.mark.asyncio
async def test_tool_has_required_protocol_properties() -> None:
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    await mount(coordinator)

    tool = coordinator.mount.call_args[0][1]
    assert isinstance(tool.name, str) and tool.name == "claim_ledger"
    assert isinstance(tool.description, str) and tool.description
    assert isinstance(tool.input_schema, dict)
    assert "operation" in tool.input_schema["properties"]
    assert callable(tool.execute)


@pytest.mark.asyncio
async def test_mount_respects_run_dir_config() -> None:
    coordinator = MagicMock()
    coordinator.mount = AsyncMock()

    await mount(coordinator, config={"run_dir": "custom-dir"})

    tool = coordinator.mount.call_args[0][1]
    assert tool.run_dir == "custom-dir"
