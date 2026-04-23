import pytest

from agent_engine.tools.response_tools import (
    RESPONSE_TOOL_NAMES,
    build_response_mcp_server,
    build_response_mcp_tools,
)


def _tool(name: str):
    for tool in build_response_mcp_tools():
        if tool.name == name:
            return tool
    raise AssertionError(f"Tool {name} not built")


@pytest.mark.asyncio
async def test_stay_silent_returns_acknowledgement():
    stay_silent = _tool("stay_silent")
    result = await stay_silent.handler({"reason": "not for me"})
    text = result["content"][0]["text"]
    assert "acknowledged" in text.lower()
    assert "no additional text" in text.lower() or "final reply" in text.lower()


@pytest.mark.asyncio
async def test_stay_silent_tolerates_missing_reason():
    stay_silent = _tool("stay_silent")
    result = await stay_silent.handler({})
    assert "content" in result


def test_build_server_returns_mcp_config():
    server = build_response_mcp_server()
    assert server is not None


def test_tool_names_match_mcp_prefix():
    assert RESPONSE_TOOL_NAMES == ("mcp__response__stay_silent",)
