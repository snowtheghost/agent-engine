from typing import Any

import structlog
from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

logger = structlog.get_logger(__name__)


def build_response_mcp_tools() -> list[SdkMcpTool[Any]]:

    @tool(
        name="stay_silent",
        description=(
            "Choose not to reply to the user this turn. Use when the incoming "
            "message is not for you, has already been answered by someone else, "
            "or does not need a response. Takes a short reason for logging."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short reason the response is being skipped.",
                },
            },
            "required": ["reason"],
        },
    )
    async def stay_silent(arguments: dict[str, Any]) -> dict[str, Any]:
        reason = str(arguments.get("reason", "")).strip() or "(no reason given)"
        logger.info("agent_stay_silent", reason=reason)
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Acknowledged. Do not produce a final reply this turn; "
                        "end your response with no additional text."
                    ),
                }
            ]
        }

    return [stay_silent]


def build_response_mcp_server() -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name="response",
        version="0.1.0",
        tools=build_response_mcp_tools(),
    )


RESPONSE_TOOL_NAMES: tuple[str, ...] = ("mcp__response__stay_silent",)
