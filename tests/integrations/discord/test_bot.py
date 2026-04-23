from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from agent_engine.core.run.model.run_result import RunResult
from agent_engine.integrations.discord.bot import DiscordIntake

CONFIGURED_CHANNEL_ID = 1000
OTHER_CHANNEL_ID = 2000
MESSAGE_ID = 42
THREAD_ALREADY_EXISTS_CODE = 160004


@dataclass
class FakeAuthor:
    bot: bool = False
    id: int = 1


@dataclass
class FakeMessage:
    channel: Any
    id: int = MESSAGE_ID
    content: str = "hello"
    author: FakeAuthor = field(default_factory=FakeAuthor)
    mentions: list[Any] = field(default_factory=list)
    create_thread: AsyncMock = field(default_factory=AsyncMock)


def _text_channel(channel_id: int) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    return channel


def _thread(parent_id: int, thread_id: int = 555) -> MagicMock:
    thread = MagicMock(spec=discord.Thread)
    thread.id = thread_id
    thread.parent_id = parent_id
    thread.send = AsyncMock()
    thread.typing = MagicMock()
    thread.typing.return_value.__aenter__ = AsyncMock()
    thread.typing.return_value.__aexit__ = AsyncMock()
    return thread


def _run_service_returning(text: str = "done") -> MagicMock:
    service = MagicMock()
    service.dispatch = AsyncMock(
        return_value=RunResult(
            run_id="r1",
            success=True,
            summary=text,
            error=None,
            duration_ms=1,
            cost_usd=0.0,
            turns=1,
            resume_handle=None,
        )
    )
    service.submit_message = AsyncMock(
        return_value=RunResult(
            run_id="r1",
            success=True,
            summary=text,
            error=None,
            duration_ms=1,
            cost_usd=0.0,
            turns=1,
            resume_handle=None,
        )
    )
    return service


def _build_intake(run_service: MagicMock | None = None) -> DiscordIntake:
    return DiscordIntake(
        token="fake-token",
        channel_id=CONFIGURED_CHANNEL_ID,
        run_service=run_service or _run_service_returning(),
    )


def test_constructor_rejects_missing_token() -> None:
    with pytest.raises(ValueError):
        DiscordIntake(token="", channel_id=CONFIGURED_CHANNEL_ID, run_service=MagicMock())


def test_constructor_rejects_missing_channel_id() -> None:
    with pytest.raises(ValueError):
        DiscordIntake(token="t", channel_id=0, run_service=MagicMock())


def test_matches_configured_channel_accepts_configured_text_channel() -> None:
    intake = _build_intake()
    message = FakeMessage(channel=_text_channel(CONFIGURED_CHANNEL_ID))
    assert intake._matches_configured_channel(message) is True


def test_matches_configured_channel_rejects_other_text_channel() -> None:
    intake = _build_intake()
    message = FakeMessage(channel=_text_channel(OTHER_CHANNEL_ID))
    assert intake._matches_configured_channel(message) is False


def test_matches_configured_channel_accepts_thread_under_configured_parent() -> None:
    intake = _build_intake()
    message = FakeMessage(channel=_thread(parent_id=CONFIGURED_CHANNEL_ID))
    assert intake._matches_configured_channel(message) is True


def test_matches_configured_channel_rejects_thread_under_other_parent() -> None:
    intake = _build_intake()
    message = FakeMessage(channel=_thread(parent_id=OTHER_CHANNEL_ID))
    assert intake._matches_configured_channel(message) is False


def test_matches_configured_channel_rejects_thread_with_missing_parent_id() -> None:
    intake = _build_intake()
    message = FakeMessage(channel=_thread(parent_id=None))
    assert intake._matches_configured_channel(message) is False


def test_matches_configured_channel_rejects_dm_channel() -> None:
    intake = _build_intake()
    dm_channel = MagicMock(spec=discord.DMChannel)
    dm_channel.id = CONFIGURED_CHANNEL_ID
    message = FakeMessage(channel=dm_channel)
    assert intake._matches_configured_channel(message) is False


@pytest.mark.asyncio
async def test_ensure_thread_returns_new_thread_when_none_exists() -> None:
    intake = _build_intake()
    channel = _text_channel(CONFIGURED_CHANNEL_ID)
    new_thread = _thread(parent_id=CONFIGURED_CHANNEL_ID)
    message = FakeMessage(channel=channel)
    message.create_thread = AsyncMock(return_value=new_thread)

    result = await intake._ensure_thread(channel, message)

    assert result is new_thread
    message.create_thread.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_thread_reuses_cached_thread_on_160004() -> None:
    intake = _build_intake()
    channel = _text_channel(CONFIGURED_CHANNEL_ID)
    existing = _thread(parent_id=CONFIGURED_CHANNEL_ID, thread_id=MESSAGE_ID)
    channel.get_thread = MagicMock(return_value=existing)

    response = MagicMock()
    response.status = 400
    error = discord.HTTPException(response=response, message="thread exists")
    error.code = THREAD_ALREADY_EXISTS_CODE

    message = FakeMessage(channel=channel)
    message.create_thread = AsyncMock(side_effect=error)

    result = await intake._ensure_thread(channel, message)

    assert result is existing
    channel.get_thread.assert_called_once_with(MESSAGE_ID)


@pytest.mark.asyncio
async def test_ensure_thread_fetches_thread_when_cache_miss_on_160004() -> None:
    intake = _build_intake()
    channel = _text_channel(CONFIGURED_CHANNEL_ID)
    channel.get_thread = MagicMock(return_value=None)
    existing = _thread(parent_id=CONFIGURED_CHANNEL_ID, thread_id=MESSAGE_ID)
    channel.guild = MagicMock()
    channel.guild.fetch_channel = AsyncMock(return_value=existing)

    response = MagicMock()
    response.status = 400
    error = discord.HTTPException(response=response, message="thread exists")
    error.code = THREAD_ALREADY_EXISTS_CODE

    message = FakeMessage(channel=channel)
    message.create_thread = AsyncMock(side_effect=error)

    result = await intake._ensure_thread(channel, message)

    assert result is existing
    channel.guild.fetch_channel.assert_awaited_once_with(MESSAGE_ID)


@pytest.mark.asyncio
async def test_ensure_thread_reraises_non_160004_http_errors() -> None:
    intake = _build_intake()
    channel = _text_channel(CONFIGURED_CHANNEL_ID)

    response = MagicMock()
    response.status = 403
    error = discord.HTTPException(response=response, message="forbidden")
    error.code = 50013

    message = FakeMessage(channel=channel)
    message.create_thread = AsyncMock(side_effect=error)

    with pytest.raises(discord.HTTPException):
        await intake._ensure_thread(channel, message)


class FakeUser:
    def __init__(self, display_name: str = "alice") -> None:
        self.bot = False
        self.display_name = display_name
        self.id = 7


@pytest.mark.asyncio
async def test_submit_and_reply_uses_submit_message() -> None:
    service = _run_service_returning("hi back")
    intake = _build_intake(run_service=service)
    thread = _thread(parent_id=CONFIGURED_CHANNEL_ID, thread_id=321)

    await intake._submit_and_reply(
        thread,
        author="alice",
        content="ping",
        resume_key="321",
    )

    service.submit_message.assert_awaited_once_with(
        resume_key="321",
        author="alice",
        content="ping",
    )
    thread.send.assert_awaited()


@pytest.mark.asyncio
async def test_submit_and_reply_sends_nothing_when_none_returned() -> None:
    service = _run_service_returning()
    service.submit_message = AsyncMock(return_value=None)
    intake = _build_intake(run_service=service)
    thread = _thread(parent_id=CONFIGURED_CHANNEL_ID, thread_id=321)

    await intake._submit_and_reply(
        thread,
        author="alice",
        content="ping",
        resume_key="321",
    )

    thread.send.assert_not_called()


@pytest.mark.asyncio
async def test_submit_and_reply_sends_nothing_when_summary_and_error_empty() -> None:
    service = _run_service_returning()
    service.submit_message = AsyncMock(
        return_value=RunResult(
            run_id="r1",
            success=True,
            summary="",
            error=None,
            duration_ms=1,
            cost_usd=0.0,
            turns=1,
            resume_handle=None,
        )
    )
    intake = _build_intake(run_service=service)
    thread = _thread(parent_id=CONFIGURED_CHANNEL_ID, thread_id=321)

    await intake._submit_and_reply(
        thread,
        author="alice",
        content="ping",
        resume_key="321",
    )

    thread.send.assert_not_called()
