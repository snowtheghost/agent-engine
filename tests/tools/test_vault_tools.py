import pytest

from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.infrastructure.persistence.database import open_database
from agent_engine.infrastructure.vault.in_memory_vector_index import InMemoryVectorIndex
from agent_engine.infrastructure.vault.sqlite_vault_repository import SqliteVaultRepository
from agent_engine.tools.vault_tools import (
    VAULT_TOOL_NAMES,
    build_vault_mcp_server,
    build_vault_mcp_tools,
)


@pytest.fixture()
def vault(tmp_path):
    connection = open_database(tmp_path / "test.db")
    yield VaultService(
        repository=SqliteVaultRepository(connection),
        index=InMemoryVectorIndex(),
    )
    connection.close()


def _tool(vault, name):
    for tool in build_vault_mcp_tools(vault):
        if tool.name == name:
            return tool
    raise AssertionError(f"Tool {name} not built")


@pytest.mark.asyncio
async def test_write_tool_creates_entry(vault):
    tool = _tool(vault, "vault_write")
    result = await tool.handler(
        {"kind": "decision", "title": "T", "body": "B"}
    )
    assert "Wrote vault entry" in result["content"][0]["text"]
    assert vault.count() == 1


@pytest.mark.asyncio
async def test_search_tool_returns_hit(vault):
    write = _tool(vault, "vault_write")
    await write.handler({"kind": "note", "title": "auth flow", "body": "we use oauth pkce"})
    search = _tool(vault, "vault_search")
    result = await search.handler({"query": "oauth", "limit": 5})
    text = result["content"][0]["text"]
    assert "Found 1 entries" in text
    assert "auth flow" in text


@pytest.mark.asyncio
async def test_search_tool_reports_empty(vault):
    search = _tool(vault, "vault_search")
    result = await search.handler({"query": "anything"})
    assert "No vault entries matched" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_recall_missing(vault):
    recall = _tool(vault, "vault_recall")
    result = await recall.handler({"entry_id": "nope"})
    assert "No entry with id" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_recall_returns_full_body(vault):
    write = _tool(vault, "vault_write")
    wrote = await write.handler({"kind": "note", "title": "T", "body": "FULL BODY"})
    entry_id = wrote["content"][0]["text"].split()[3]
    recall = _tool(vault, "vault_recall")
    result = await recall.handler({"entry_id": entry_id})
    assert "FULL BODY" in result["content"][0]["text"]


def test_build_server_returns_mcp_config(vault):
    server = build_vault_mcp_server(vault)
    assert server is not None


def test_tool_names_match_mcp_prefix():
    assert VAULT_TOOL_NAMES == (
        "mcp__vault__vault_write",
        "mcp__vault__vault_search",
        "mcp__vault__vault_recall",
    )
