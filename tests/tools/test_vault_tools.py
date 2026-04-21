import pytest

from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.infrastructure.vault.file_vault_scanner import FileVaultScanner
from agent_engine.infrastructure.vault.in_memory_vault_index import InMemoryVaultIndex
from agent_engine.tools.vault_tools import (
    VAULT_TOOL_NAMES,
    build_vault_mcp_server,
    build_vault_mcp_tools,
)


@pytest.fixture()
def vault(tmp_path):
    directory = tmp_path / "vault"
    directory.mkdir()
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=directory, index=index)
    return VaultService(directory=directory, index=index, scanner=scanner)


def _tool(vault, name):
    for tool in build_vault_mcp_tools(vault):
        if tool.name == name:
            return tool
    raise AssertionError(f"Tool {name} not built")


@pytest.mark.asyncio
async def test_write_tool_creates_entry(vault):
    tool = _tool(vault, "vault_write")
    result = await tool.handler(
        {"title": "Decision note", "content": "We chose oauth pkce for the auth flow."}
    )
    assert "Wrote vault entry" in result["content"][0]["text"]
    assert vault.count() >= 1


@pytest.mark.asyncio
async def test_search_tool_returns_hit(vault):
    write = _tool(vault, "vault_write")
    await write.handler({"title": "Auth", "content": "oauth pkce flow details here long enough."})
    search = _tool(vault, "vault_search")
    result = await search.handler({"query": "oauth", "limit": 5})
    text = result["content"][0]["text"]
    assert "Found" in text
    assert ".md" in text


@pytest.mark.asyncio
async def test_search_tool_reports_empty(vault):
    search = _tool(vault, "vault_search")
    result = await search.handler({"query": "anything"})
    assert "No vault chunks matched" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_recall_missing(vault):
    recall = _tool(vault, "vault_recall")
    result = await recall.handler({"path": "nope.md"})
    assert "No vault file" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_recall_returns_full_body(vault):
    write = _tool(vault, "vault_write")
    wrote = await write.handler(
        {"title": "FullBody", "content": "Body content with enough length to pass."}
    )
    # path is after "at " in the text
    path_line = wrote["content"][0]["text"]
    rel = path_line.split("at ")[-1].strip()
    # rel is absolute; recall supports absolute when under vault dir
    recall = _tool(vault, "vault_recall")
    result = await recall.handler({"path": rel})
    assert "# FullBody" in result["content"][0]["text"]


def test_build_server_returns_mcp_config(vault):
    server = build_vault_mcp_server(vault)
    assert server is not None


def test_tool_names_match_mcp_prefix():
    assert VAULT_TOOL_NAMES == (
        "mcp__vault__vault_write",
        "mcp__vault__vault_search",
        "mcp__vault__vault_recall",
    )
