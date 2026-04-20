import asyncio

import discord
import structlog

from agent_engine.application.integration.intake import Intake
from agent_engine.application.run.service.run_service import RunService

logger = structlog.get_logger(__name__)


class DiscordIntake(Intake):

    def __init__(
        self,
        *,
        token: str,
        channel_id: int | None,
        run_service: RunService,
        character_limit: int = 2000,
    ) -> None:
        self._token = token
        self._channel_id = channel_id
        self._run_service = run_service
        self._character_limit = character_limit

        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        self._client = discord.Client(intents=intents)

        self._register_handlers()
        self._task: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        return "discord"

    async def start(self) -> None:
        self._task = asyncio.create_task(self._client.start(self._token))
        logger.info("discord_intake_starting")

    async def stop(self) -> None:
        await self._client.close()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("discord_intake_stop_timeout")
                self._task.cancel()
        logger.info("discord_intake_stopped")

    def _register_handlers(self) -> None:

        @self._client.event
        async def on_ready() -> None:
            logger.info(
                "discord_ready",
                user=str(self._client.user),
                channel=self._channel_id,
            )

        @self._client.event
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return
            if message.author == self._client.user:
                return

            channel = message.channel
            if isinstance(channel, discord.Thread):
                parent = channel.parent
                if (
                    self._channel_id is not None
                    and parent is not None
                    and parent.id != self._channel_id
                ):
                    return
                await self._handle_thread_message(channel, message)
                return

            if isinstance(channel, discord.TextChannel):
                if self._channel_id is not None and channel.id != self._channel_id:
                    return
                await self._handle_channel_message(channel, message)

    async def _handle_channel_message(
        self,
        channel: discord.TextChannel,
        message: discord.Message,
    ) -> None:
        title = message.content[:80] if message.content else f"Run {message.id}"
        thread = await message.create_thread(name=title, auto_archive_duration=1440)
        await self._dispatch_and_reply(thread, message.content, resume_key=str(thread.id))

    async def _handle_thread_message(
        self,
        thread: discord.Thread,
        message: discord.Message,
    ) -> None:
        await self._dispatch_and_reply(thread, message.content, resume_key=str(thread.id))

    async def _dispatch_and_reply(
        self,
        thread: discord.Thread,
        prompt: str,
        *,
        resume_key: str,
    ) -> None:
        try:
            async with thread.typing():
                result = await self._run_service.dispatch(prompt, resume_key=resume_key)
        except Exception as error:
            logger.exception("discord_dispatch_failed")
            await self._send_chunked(thread, f"[error] {error}")
            return

        text = result.summary if result.summary else (result.error or "(no output)")
        if not result.success and result.error and not text.startswith("[error]"):
            text = f"[error] {text}"
        await self._send_chunked(thread, text)

    async def _send_chunked(self, thread: discord.Thread, text: str) -> None:
        if not text:
            return
        for chunk_start in range(0, len(text), self._character_limit):
            chunk = text[chunk_start : chunk_start + self._character_limit]
            await thread.send(chunk)
