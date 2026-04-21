from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from agent_engine.application.thread.service.thread_service import ThreadService
from agent_engine.core.thread.model.thread import AttachmentMetadata, Thread, ThreadEntry


def build_thread_mcp_tools(thread_service: ThreadService) -> list[SdkMcpTool[Any]]:

    @tool(
        name="thread_recall",
        description=(
            "Return the full transcript of a durable thread keyed by "
            "resume_key. Entries are formatted as author-tagged blocks; "
            "attachments are summarised with path and optional vision text."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "resume_key": {
                    "type": "string",
                    "description": "Conversation identity used by the integration.",
                },
            },
            "required": ["resume_key"],
        },
    )
    async def thread_recall(arguments: dict[str, Any]) -> dict[str, Any]:
        thread = thread_service.get_thread(arguments["resume_key"])
        if thread is None:
            text = f"No thread found for resume_key {arguments['resume_key']}"
        else:
            text = _format_thread(thread)
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        name="thread_list",
        description=(
            "List durable thread resume_keys, most recently updated first."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of threads to return.",
                    "default": 20,
                },
            },
            "required": [],
        },
    )
    async def thread_list(arguments: dict[str, Any]) -> dict[str, Any]:
        limit = int(arguments.get("limit", 20))
        keys = thread_service.list_threads(limit=limit)
        if not keys:
            text = "No threads stored."
        else:
            text = "\n".join(keys)
        return {"content": [{"type": "text", "text": text}]}

    return [thread_recall, thread_list]


def build_thread_mcp_server(thread_service: ThreadService) -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name="thread",
        version="0.1.0",
        tools=build_thread_mcp_tools(thread_service),
    )


def _format_thread(thread: Thread) -> str:
    if not thread.entries:
        return f"[thread {thread.resume_key} has no entries]"
    blocks = [_format_entry(entry) for entry in thread.entries]
    return "\n\n".join(blocks)


def _format_entry(entry: ThreadEntry) -> str:
    parts: list[str] = [f"[From: {entry.author}] {entry.timestamp.isoformat()}", ""]
    parts.append(entry.content)
    if entry.attachments:
        parts.append("")
        parts.append("[Attachments:]")
        for attachment in entry.attachments:
            parts.append(_format_attachment(attachment))
            if attachment.description:
                parts.append(f"    [Vision: {attachment.description}]")
    return "\n".join(parts)


def _format_attachment(attachment: AttachmentMetadata) -> str:
    size_kb = attachment.size / 1024
    if size_kb >= 1024:
        size_str = f"{size_kb / 1024:.1f} MB"
    else:
        size_str = f"{size_kb:.0f} KB"
    return (
        f"  {attachment.filename} ({attachment.content_type}, {size_str}): "
        f"{attachment.path}"
    )


THREAD_TOOL_NAMES: tuple[str, ...] = (
    "mcp__thread__thread_recall",
    "mcp__thread__thread_list",
)
