from typing import Any

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from agent_engine.application.vault.service.vault_service import VaultService


def build_vault_mcp_tools(vault: VaultService) -> list[SdkMcpTool[Any]]:

    @tool(
        name="vault_write",
        description=(
            "Write a new entry to the project's persistent knowledge vault. "
            "Every session contributes to the vault; every session can search it. "
            "Use this to record decisions, patterns, gotchas, architecture notes, "
            "and anything the next session would benefit from knowing."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Free-form category tag: decision, pattern, gotcha, api-note, etc.",
                },
                "title": {
                    "type": "string",
                    "description": "Short, searchable title.",
                },
                "body": {
                    "type": "string",
                    "description": "Full content of the entry.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for filtering.",
                    "default": [],
                },
            },
            "required": ["kind", "title", "body"],
        },
    )
    async def vault_write(arguments: dict[str, Any]) -> dict[str, Any]:
        entry = vault.write(
            kind=arguments["kind"],
            title=arguments["title"],
            body=arguments["body"],
            tags=tuple(arguments.get("tags", []) or []),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Wrote vault entry {entry.entry_id} "
                        f"(kind={entry.kind}, title={entry.title!r})"
                    ),
                }
            ]
        }

    @tool(
        name="vault_search",
        description=(
            "Search the project's knowledge vault by meaning. "
            "Returns top-k entries ranked by semantic similarity."
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
            },
            "required": ["query"],
        },
    )
    async def vault_search(arguments: dict[str, Any]) -> dict[str, Any]:
        hits = vault.search(arguments["query"], int(arguments.get("limit", 5)))
        if not hits:
            text = "No vault entries matched."
        else:
            lines = [f"Found {len(hits)} entries:"]
            for hit in hits:
                tags = ", ".join(hit.entry.tags) if hit.entry.tags else "-"
                body_preview = hit.entry.body.replace("\n", " ")[:200]
                lines.append(
                    f"\n[{hit.score:.3f}] {hit.entry.entry_id}"
                    f"\n  kind: {hit.entry.kind}"
                    f"\n  title: {hit.entry.title}"
                    f"\n  tags: {tags}"
                    f"\n  path: {hit.path}"
                    f"\n  preview: {body_preview}"
                )
            text = "\n".join(lines)
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        name="vault_recall",
        description="Fetch the full body of a specific vault entry by its id.",
        input_schema={
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "The entry id."},
            },
            "required": ["entry_id"],
        },
    )
    async def vault_recall(arguments: dict[str, Any]) -> dict[str, Any]:
        entry = vault.recall(arguments["entry_id"])
        if entry is None:
            return {
                "content": [
                    {"type": "text", "text": f"No entry with id {arguments['entry_id']}"}
                ]
            }
        tags = ", ".join(entry.tags) if entry.tags else "-"
        text = (
            f"Entry {entry.entry_id}\n"
            f"Kind: {entry.kind}\n"
            f"Title: {entry.title}\n"
            f"Tags: {tags}\n"
            f"Created: {entry.created_at.isoformat()}\n"
            f"\n{entry.body}"
        )
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
