import asyncio
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import structlog
from claude_agent_sdk import ClaudeSDKClient, Message, ResultMessage

logger = structlog.get_logger(__name__)

try:
    from claude_agent_sdk._errors import MessageParseError
    from claude_agent_sdk._internal.message_parser import parse_message as _sdk_parse_message

    _SDK_INTERNALS_AVAILABLE = True
except ImportError:
    _SDK_INTERNALS_AVAILABLE = False
    MessageParseError = Exception
    _sdk_parse_message = None


_KNOWN_SDK_EVENT_TYPES = {"rate_limit_event"}


def get_sdk_process_pid(client: ClaudeSDKClient) -> int | None:
    transport = getattr(client, "_transport", None)
    if transport is None:
        return None
    process = getattr(transport, "_process", None)
    if process is None:
        return None
    return process.pid


def _get_raw_message_stream(client: ClaudeSDKClient) -> Any:
    query = getattr(client, "_query", None)
    if query is None:
        raise AttributeError(
            "ClaudeSDKClient._query unavailable. SDK version may be incompatible."
        )
    return query.receive_messages()


async def resilient_receive(client: ClaudeSDKClient) -> AsyncGenerator[Message, None]:
    if not _SDK_INTERNALS_AVAILABLE or _sdk_parse_message is None:
        raise RuntimeError(
            "claude_agent_sdk internal APIs unavailable. SDK version may be incompatible."
        )

    async for data in _get_raw_message_stream(client):
        try:
            message = _sdk_parse_message(data)
        except MessageParseError:
            message_type = data.get("type", "") if isinstance(data, dict) else ""
            if message_type not in _KNOWN_SDK_EVENT_TYPES:
                logger.debug("unrecognized_sdk_message", type=message_type)
            continue
        yield message
        if isinstance(message, ResultMessage):
            return


def get_child_pids(pid: int) -> list[int]:
    try:
        children_file = Path(f"/proc/{pid}/task/{pid}/children")
        if children_file.exists():
            text = children_file.read_text().strip()
            if text:
                return [int(p) for p in text.split()]
    except Exception:
        logger.debug("get_child_pids_failed", pid=pid)
    return []


async def wait_for_children(pid: int, timeout: float = 120.0) -> None:
    deadline = time.time() + timeout
    poll_interval = 5.0

    while time.time() < deadline:
        children = get_child_pids(pid)
        if not children:
            return
        logger.info(
            "waiting_for_subagents",
            sdk_pid=pid,
            child_pids=children,
            remaining_s=int(deadline - time.time()),
        )
        await asyncio.sleep(poll_interval)

    children = get_child_pids(pid)
    if children:
        logger.warning(
            "subagent_wait_timeout",
            sdk_pid=pid,
            remaining_children=children,
            timeout_s=timeout,
        )
