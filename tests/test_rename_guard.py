import pytest

from psu_mcp.server import call_tool


@pytest.mark.asyncio
async def test_legacy_project_path_rejected():
    """Hard rename: passing legacy project_path to a logging tool fails loudly."""
    result = await call_tool("yank_restore", {"project_path": "/tmp/x"})
    assert result["ok"] is False
    assert result["error"] == "renamed_argument"
    assert "engagement_path" in result["message"]
