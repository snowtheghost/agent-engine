from datetime import UTC, datetime

import pytest

from agent_engine.application.thread.service.thread_service import ThreadService
from agent_engine.core.thread.model.thread import ThreadEntry
from agent_engine.infrastructure.thread.in_memory_thread_index import InMemoryThreadIndex
from agent_engine.tools.thread_tools import build_thread_mcp_tools
from tests.application.thread.test_thread_service import InMemoryThreadRepository


def _chunk_content(content: str) -> ThreadEntry:
    return ThreadEntry(
        author="alice",
        content=content,
        attachments=(),
        timestamp=datetime(2026, 4, 22, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_thread_search_tool_returns_hits():
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)
    index = InMemoryThreadIndex()

    from agent_engine.infrastructure.thread.chunker import chunk_entry

    entry = _chunk_content("discuss icebox monorepo migration progress here today")
    repository.append("k1", entry)
    chunk = chunk_entry("k1", 0, entry)
    assert chunk is not None
    index.upsert([chunk])

    tools = build_thread_mcp_tools(service, index=index)
    by_name = {tool.name: tool for tool in tools}
    assert "thread_search" in by_name

    result = await by_name["thread_search"].handler({"query": "monorepo migration"})
    text = result["content"][0]["text"]
    assert "k1" in text
    assert "1 entries" in text or "Found 1 entries" in text


@pytest.mark.asyncio
async def test_thread_search_tool_without_index_falls_back():
    repository = InMemoryThreadRepository()
    service = ThreadService(repository)

    tools = build_thread_mcp_tools(service, index=None)
    by_name = {tool.name: tool for tool in tools}

    result = await by_name["thread_search"].handler({"query": "anything"})
    text = result["content"][0]["text"]
    assert "not available" in text.lower()
