from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from agent_engine.application.vault.service.vault_service import VaultService


def build_vault_mcp_tools(vault: VaultService) -> list[SdkMcpTool[Any]]:

    @tool(
        name="vault_write",
        description=(
            "Write a new markdown entry to the project's vault. "
            "Files are chunked and indexed semantically. Use for decisions, "
            "patterns, gotchas, architecture notes — anything a future session "
            "should be able to find by meaning."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the entry. Used for the H1 heading and file name.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Full markdown body. Use `## Sections` and `### Subsections` — "
                        "each becomes a separately indexed chunk."
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional frontmatter tags.",
                    "default": [],
                },
                "subdirectory": {
                    "type": "string",
                    "description": "Optional subdirectory under the vault directory.",
                },
            },
            "required": ["title", "content"],
        },
    )
    async def vault_write(arguments: dict[str, Any]) -> dict[str, Any]:
        path = vault.write(
            title=arguments["title"],
            content=arguments["content"],
            tags=tuple(arguments.get("tags", []) or []),
            subdirectory=arguments.get("subdirectory"),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Wrote vault entry at {path}",
                }
            ]
        }

    @tool(
        name="vault_search",
        description=(
            "Search the project's vault by meaning. Returns top-k chunks with "
            "file path, heading, and similarity score."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language question or topic.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return.",
                    "default": 5,
                },
                "file": {
                    "type": "string",
                    "description": "Restrict to chunks from this file path (relative to vault).",
                },
            },
            "required": ["query"],
        },
    )
    async def vault_search(arguments: dict[str, Any]) -> dict[str, Any]:
        hits = vault.search(
            arguments["query"],
            int(arguments.get("limit", 5)),
            file_filter=arguments.get("file"),
        )
        if not hits:
            text = "No vault chunks matched."
        else:
            lines = [f"Found {len(hits)} chunks:"]
            for hit in hits:
                preview = hit.chunk.content.replace("\n", " ")[:240]
                lines.append(
                    f"\n[{hit.score:.3f}] {hit.chunk.file_path}"
                    f"\n  heading: {hit.chunk.heading}"
                    f"\n  preview: {preview}"
                )
            text = "\n".join(lines)
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        name="vault_recall",
        description="Read the full markdown of a vault file by its relative path.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the vault directory.",
                },
            },
            "required": ["path"],
        },
    )
    async def vault_recall(arguments: dict[str, Any]) -> dict[str, Any]:
        body = vault.recall(arguments["path"])
        if body is None:
            text = f"No vault file at {arguments['path']}"
        else:
            text = body
        return {"content": [{"type": "text", "text": text}]}

    return [vault_write, vault_search, vault_recall]


def build_vault_mcp_server(vault: VaultService) -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name="vault",
        version="0.1.0",
        tools=build_vault_mcp_tools(vault),
    )


VAULT_TOOL_NAMES: tuple[str, ...] = (
    "mcp__vault__vault_write",
    "mcp__vault__vault_search",
    "mcp__vault__vault_recall",
)
