from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_engine.core.run.model.run_result import RunResult
from agent_engine.integrations.slack.bot import SlackIntake

CONFIGURED_CHANNEL = "C123"
OTHER_CHANNEL = "C999"
USER_ID = "U123"
MESSAGE_TS = "1700000000.000100"
THREAD_TS = "1700000000.000000"


def _event(
    channel: str = CONFIGURED_CHANNEL,
    user: str = USER_ID,
    text: str = "hello",
    ts: str = MESSAGE_TS,
    thread_ts: str | None = None,
    subtype: str | None = None,
    bot_id: str | None = None,
) -> dict:
    event: dict = {
        "channel": channel,
        "user": user,
        "text": text,
        "ts": ts,
    }
    if thread_ts is not None:
        event["thread_ts"] = thread_ts
    if subtype is not None:
        event["subtype"] = subtype
    if bot_id is not None:
        event["bot_id"] = bot_id
    return event


def _client() -> MagicMock:
    client = MagicMock()
    client.users_info = AsyncMock(
        return_value={
            "user": {
                "real_name": "Alice Real",
                "profile": {"display_name": "alice"},
            }
        }
    )
    client.reactions_add = AsyncMock()
    client.reactions_remove = AsyncMock()
    client.chat_postMessage = AsyncMock()
    return client


def _intake(run_service: MagicMock, character_limit: int = 40000) -> SlackIntake:
    with (
        patch("agent_engine.integrations.slack.bot.AsyncApp") as app_cls,
        patch("agent_engine.integrations.slack.bot.AsyncSocketModeHandler"),
    ):
        app_instance = MagicMock()
        app_instance.event = MagicMock(return_value=lambda fn: fn)
        app_cls.return_value = app_instance
        return SlackIntake(
            bot_token="xoxb-test",
            app_token="xapp-test",
            monitored_channels=(CONFIGURED_CHANNEL,),
            run_service=run_service,
            character_limit=character_limit,
        )


def _run_service(result: RunResult | None) -> MagicMock:
    service = MagicMock()
    service.submit_message = AsyncMock(return_value=result)
    return service


def _ok_result(summary: str = "hi back") -> RunResult:
    return RunResult(
        run_id="test-run",
        success=True,
        summary=summary,
        error=None,
        duration_ms=1,
        cost_usd=0.0,
        turns=1,
        resume_handle=None,
    )


@pytest.mark.asyncio
async def test_message_in_monitored_channel_dispatches():
    service = _run_service(_ok_result())
    intake = _intake(service)

    await intake._handle_message(_event(), _client())

    service.submit_message.assert_awaited_once()
    kwargs = service.submit_message.await_args.kwargs
    assert kwargs["resume_key"] == f"slack:{CONFIGURED_CHANNEL}:{MESSAGE_TS}"
    assert kwargs["author"] == "alice"
    assert kwargs["content"] == "hello"


@pytest.mark.asyncio
async def test_thread_reply_uses_thread_ts_as_resume_key():
    service = _run_service(_ok_result())
    intake = _intake(service)

    await intake._handle_message(_event(thread_ts=THREAD_TS, ts=MESSAGE_TS), _client())

    kwargs = service.submit_message.await_args.kwargs
    assert kwargs["resume_key"] == f"slack:{CONFIGURED_CHANNEL}:{THREAD_TS}"


@pytest.mark.asyncio
async def test_ignores_other_channels():
    service = _run_service(_ok_result())
    intake = _intake(service)

    await intake._handle_message(_event(channel=OTHER_CHANNEL), _client())

    service.submit_message.assert_not_called()


@pytest.mark.asyncio
async def test_ignores_bot_messages():
    service = _run_service(_ok_result())
    intake = _intake(service)

    await intake._handle_message(_event(bot_id="B123"), _client())

    service.submit_message.assert_not_called()


@pytest.mark.asyncio
async def test_ignores_subtype_messages():
    service = _run_service(_ok_result())
    intake = _intake(service)

    await intake._handle_message(_event(subtype="message_changed"), _client())

    service.submit_message.assert_not_called()


@pytest.mark.asyncio
async def test_ignores_empty_text():
    service = _run_service(_ok_result())
    intake = _intake(service)

    await intake._handle_message(_event(text="   "), _client())

    service.submit_message.assert_not_called()


@pytest.mark.asyncio
async def test_posts_reply_in_thread():
    service = _run_service(_ok_result("the agent reply"))
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.chat_postMessage.assert_awaited_once()
    call = client.chat_postMessage.await_args
    assert call.kwargs["channel"] == CONFIGURED_CHANNEL
    assert call.kwargs["thread_ts"] == MESSAGE_TS
    assert call.kwargs["text"] == "the agent reply"


@pytest.mark.asyncio
async def test_chunks_long_replies():
    service = _run_service(_ok_result("a" * 25))
    intake = _intake(service, character_limit=10)
    client = _client()

    await intake._handle_message(_event(), client)

    assert client.chat_postMessage.await_count == 3


@pytest.mark.asyncio
async def test_no_reply_when_submit_returns_none():
    service = _run_service(None)
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_no_reply_when_summary_and_error_empty():
    silent_result = RunResult(
        run_id="test-run",
        success=True,
        summary="",
        error=None,
        duration_ms=1,
        cost_usd=0.0,
        turns=1,
        resume_handle=None,
    )
    service = _run_service(silent_result)
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_reaction_added_before_dispatch_and_removed_after_reply():
    service = _run_service(_ok_result())
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.reactions_add.assert_awaited_once()
    add_kwargs = client.reactions_add.await_args.kwargs
    assert add_kwargs["channel"] == CONFIGURED_CHANNEL
    assert add_kwargs["timestamp"] == MESSAGE_TS
    assert add_kwargs["name"] == "eyes"

    client.reactions_remove.assert_awaited_once()
    remove_kwargs = client.reactions_remove.await_args.kwargs
    assert remove_kwargs["channel"] == CONFIGURED_CHANNEL
    assert remove_kwargs["timestamp"] == MESSAGE_TS
    assert remove_kwargs["name"] == "eyes"


@pytest.mark.asyncio
async def test_reaction_removed_on_dispatch_error():
    service = MagicMock()
    service.submit_message = AsyncMock(side_effect=RuntimeError("boom"))
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.reactions_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_reaction_removed_when_submit_returns_none():
    service = _run_service(None)
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.reactions_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_reaction_removed_when_summary_and_error_empty():
    silent_result = RunResult(
        run_id="test-run",
        success=True,
        summary="",
        error=None,
        duration_ms=1,
        cost_usd=0.0,
        turns=1,
        resume_handle=None,
    )
    service = _run_service(silent_result)
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.reactions_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_reaction_remove_failure_does_not_raise():
    service = _run_service(_ok_result())
    intake = _intake(service)
    client = _client()
    client.reactions_remove = AsyncMock(side_effect=RuntimeError("slack api down"))

    await intake._handle_message(_event(), client)

    client.reactions_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_name_cached_across_calls():
    service = _run_service(_ok_result())
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)
    await intake._handle_message(_event(ts="1700000001.000000"), client)

    assert client.users_info.await_count == 1


@pytest.mark.asyncio
async def test_falls_back_to_user_id_when_lookup_fails():
    service = _run_service(_ok_result())
    intake = _intake(service)
    client = _client()
    client.users_info = AsyncMock(side_effect=RuntimeError("boom"))

    await intake._handle_message(_event(), client)

    kwargs = service.submit_message.await_args.kwargs
    assert kwargs["author"] == USER_ID


@pytest.mark.asyncio
async def test_error_reply_posted_when_dispatch_fails():
    service = MagicMock()
    service.submit_message = AsyncMock(side_effect=RuntimeError("oops"))
    intake = _intake(service)
    client = _client()

    await intake._handle_message(_event(), client)

    client.chat_postMessage.assert_awaited_once()
    text = client.chat_postMessage.await_args.kwargs["text"]
    assert text.startswith("[error]")
    assert "oops" in text


def test_missing_bot_token_raises():
    with pytest.raises(ValueError, match="bot_token"):
        SlackIntake(
            bot_token="",
            app_token="xapp",
            monitored_channels=(CONFIGURED_CHANNEL,),
            run_service=MagicMock(),
        )


def test_missing_app_token_raises():
    with pytest.raises(ValueError, match="app_token"):
        SlackIntake(
            bot_token="xoxb",
            app_token="",
            monitored_channels=(CONFIGURED_CHANNEL,),
            run_service=MagicMock(),
        )


def test_empty_channels_raises():
    with pytest.raises(ValueError, match="at least one"):
        SlackIntake(
            bot_token="xoxb",
            app_token="xapp",
            monitored_channels=(),
            run_service=MagicMock(),
        )
