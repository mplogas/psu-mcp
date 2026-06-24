import pytest

from psu_mcp.server import call_tool


@pytest.mark.asyncio
async def test_legacy_project_path_rejected():
    """Hard rename: a legacy project_path arg fails loud, not silent."""
    result = await call_tool("yank_restore", {"project_path": "/tmp/x"})
    assert "engagement_path" in result["error"]
    assert "project_path" in result["error"]
