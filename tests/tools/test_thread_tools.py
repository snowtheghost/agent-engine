from datetime import UTC, datetime

import pytest

from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.application.thread.service.thread_service import ThreadService
from agent_engine.core.thread.model.thread import AttachmentMetadata, Thread, ThreadEntry
from agent_engine.tools.thread_tools import (
    THREAD_TOOL_NAMES,
    build_thread_mcp_server,
    build_thread_mcp_tools,
)


class InMemoryThreadRepository(ThreadRepository):
    def __init__(self) -> None:
        self.threads: dict[str, Thread] = {}

    def append(self, resume_key, entry):
        thread = self.threads.setdefault(resume_key, Thread(resume_key=resume_key))
        thread.entries.append(entry)
        return len(thread.entries) - 1

    def load(self, resume_key):
        return self.threads.get(resume_key)

    def delete(self, resume_key):
        return self.threads.pop(resume_key, None) is not None

    def list_keys(self):
        return list(self.threads.keys())

    def update_cursor(self, resume_key, cursor):
        thread = self.threads.setdefault(resume_key, Thread(resume_key=resume_key))
        thread.read_cursor = cursor


@pytest.fixture()
def service():
    return ThreadService(InMemoryThreadRepository())


def _tool(service, name):
    for tool in build_thread_mcp_tools(service):
        if tool.name == name:
            return tool
    raise AssertionError(f"Tool {name} not built")


@pytest.mark.asyncio
async def test_recall_returns_empty_message_when_missing(service):
    recall = _tool(service, "thread_recall")
    result = await recall.handler({"resume_key": "nope"})
    assert "No thread found" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_recall_formats_entries(service):
    service.handle_message(
        "k1",
        ThreadEntry(
            author="alice",
            content="hello",
            attachments=(),
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        ),
    )
    service.log_reply("k1", "hi there")

    recall = _tool(service, "thread_recall")
    result = await recall.handler({"resume_key": "k1"})
    text = result["content"][0]["text"]
    assert "[From: alice]" in text
    assert "[From: agent]" in text
    assert "hello" in text
    assert "hi there" in text


@pytest.mark.asyncio
async def test_recall_formats_attachments(service):
    service.handle_message(
        "k1",
        ThreadEntry(
            author="alice",
            content="pic",
            attachments=(
                AttachmentMetadata(
                    path="/tmp/a.png",
                    filename="a.png",
                    content_type="image/png",
                    size=1024,
                    description="a cat",
                ),
            ),
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    )
    recall = _tool(service, "thread_recall")
    result = await recall.handler({"resume_key": "k1"})
    text = result["content"][0]["text"]
    assert "a.png" in text
    assert "a cat" in text


@pytest.mark.asyncio
async def test_list_returns_empty_message_when_none(service):
    listing = _tool(service, "thread_list")
    result = await listing.handler({})
    assert "No threads stored" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_list_returns_keys(service):
    service.handle_message(
        "k1",
        ThreadEntry(
            author="alice",
            content="hi",
            attachments=(),
            timestamp=datetime.now(UTC),
        ),
    )
    service.handle_message(
        "k2",
        ThreadEntry(
            author="alice",
            content="hi",
            attachments=(),
            timestamp=datetime.now(UTC),
        ),
    )
    listing = _tool(service, "thread_list")
    result = await listing.handler({})
    text = result["content"][0]["text"]
    assert "k1" in text
    assert "k2" in text


def test_build_server_returns_mcp_config(service):
    server = build_thread_mcp_server(service)
    assert server is not None


def test_tool_names_match_mcp_prefix():
    assert THREAD_TOOL_NAMES == (
        "mcp__thread__thread_recall",
        "mcp__thread__thread_list",
        "mcp__thread__thread_search",
    )
