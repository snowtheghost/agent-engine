import asyncio
from typing import Any

import structlog
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from agent_engine.application.integration.intake import Intake
from agent_engine.application.run.service.run_service import RunService

logger = structlog.get_logger(__name__)

_WORKING_REACTION = "eyes"


class SlackIntake(Intake):

    def __init__(
        self,
        *,
        bot_token: str,
        app_token: str,
        monitored_channels: tuple[str, ...],
        run_service: RunService,
        character_limit: int = 40000,
    ) -> None:
        if not bot_token:
            raise ValueError("SlackIntake requires a non-empty bot_token")
        if not app_token:
            raise ValueError("SlackIntake requires a non-empty app_token")
        if not monitored_channels:
            raise ValueError("SlackIntake requires at least one monitored channel")

        self._bot_token = bot_token
        self._app_token = app_token
        self._monitored_channels = frozenset(monitored_channels)
        self._run_service = run_service
        self._character_limit = character_limit

        self._app = AsyncApp(token=bot_token)
        self._handler = AsyncSocketModeHandler(self._app, app_token)
        self._user_name_cache: dict[str, str] = {}

        self._register_handlers()

    @property
    def name(self) -> str:
        return "slack"

    async def start(self) -> None:
        asyncio.create_task(self._handler.start_async(), name="slack-socket-mode")
        logger.info(
            "slack_intake_starting",
            monitored_channels=sorted(self._monitored_channels),
        )

    async def stop(self) -> None:
        try:
            await self._handler.close_async()
        except Exception:
            logger.exception("slack_intake_close_failed")
        logger.info("slack_intake_stopped")

    def _register_handlers(self) -> None:

        @self._app.event("message")
        async def _on_message(event: dict[str, Any], client: Any) -> None:
            await self._handle_message(event, client)

    async def _handle_message(self, event: dict[str, Any], client: Any) -> None:
        if event.get("subtype") is not None:
            return
        if event.get("bot_id"):
            return

        channel_id = event.get("channel", "")
        if channel_id not in self._monitored_channels:
            return

        user_id = event.get("user", "")
        text = event.get("text", "")
        message_ts = event.get("ts", "")
        thread_ts = event.get("thread_ts") or message_ts

        if not text.strip():
            return

        user_name = await self._resolve_user_name(client, user_id)
        resume_key = f"slack:{channel_id}:{thread_ts}"

        logger.info(
            "slack_message_received",
            channel_id=channel_id,
            user_id=user_id,
            user_name=user_name,
            thread_ts=thread_ts,
            message_ts=message_ts,
            text_preview=text[:100],
        )

        await self._react(client, channel_id, message_ts, _WORKING_REACTION)

        try:
            result = await self._run_service.submit_message(
                resume_key=resume_key,
                author=user_name,
                content=text,
            )
        except Exception as error:
            logger.exception("slack_dispatch_failed")
            await self._send_chunked(client, channel_id, thread_ts, f"[error] {error}")
            return

        if result is None:
            return

        reply_text = result.summary if result.summary else (result.error or "(no output)")
        if not result.success and result.error and not reply_text.startswith("[error]"):
            reply_text = f"[error] {reply_text}"
        await self._send_chunked(client, channel_id, thread_ts, reply_text)

    async def _resolve_user_name(self, client: Any, user_id: str) -> str:
        if not user_id:
            return "unknown"
        cached = self._user_name_cache.get(user_id)
        if cached is not None:
            return cached
        try:
            response = await client.users_info(user=user_id)
            user = response.get("user") or {}
            profile = user.get("profile") or {}
            display_name = profile.get("display_name") or ""
            real_name = user.get("real_name") or ""
            name = display_name or real_name or user_id
        except Exception:
            logger.warning("slack_user_name_resolve_failed", user_id=user_id)
            name = user_id
        self._user_name_cache[user_id] = name
        return name

    async def _react(self, client: Any, channel_id: str, message_ts: str, emoji: str) -> None:
        try:
            await client.reactions_add(channel=channel_id, timestamp=message_ts, name=emoji)
        except Exception:
            logger.debug("slack_reaction_add_failed", channel=channel_id, emoji=emoji)

    async def _send_chunked(
        self,
        client: Any,
        channel_id: str,
        thread_ts: str,
        text: str,
    ) -> None:
        if not text:
            return
        for chunk_start in range(0, len(text), self._character_limit):
            chunk = text[chunk_start : chunk_start + self._character_limit]
            try:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=chunk,
                    thread_ts=thread_ts,
                )
            except Exception:
                logger.exception(
                    "slack_post_message_failed",
                    channel=channel_id,
                    thread_ts=thread_ts,
                )
                return
