import asyncio

import discord
import structlog

from agent_engine.application.integration.intake import Intake
from agent_engine.application.run.service.run_service import RunService

logger = structlog.get_logger(__name__)

_THREAD_ALREADY_EXISTS_CODE = 160004


class DiscordIntake(Intake):

    def __init__(
        self,
        *,
        token: str,
        channel_id: int,
        run_service: RunService,
        character_limit: int = 2000,
    ) -> None:
        if not token:
            raise ValueError("DiscordIntake requires a non-empty token")
        if not channel_id:
            raise ValueError("DiscordIntake requires a channel_id")

        self._token = token
        self._channel_id = int(channel_id)
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
        logger.info("discord_intake_starting", channel_id=self._channel_id)

    async def stop(self) -> None:
        await self._client.close()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                logger.warning("discord_intake_stop_timeout")
                self._task.cancel()
        logger.info("discord_intake_stopped")

    def _root_channel_id(self, message: discord.Message) -> int | None:
        channel = message.channel
        if isinstance(channel, discord.Thread):
            return channel.parent_id
        if isinstance(channel, discord.TextChannel):
            return channel.id
        return None

    def _matches_configured_channel(self, message: discord.Message) -> bool:
        root_id = self._root_channel_id(message)
        return root_id is not None and root_id == self._channel_id

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
            if message.author.bot or message.author == self._client.user:
                return

            if not self._matches_configured_channel(message):
                logger.debug(
                    "discord_message_ignored",
                    channel_id=getattr(message.channel, "id", None),
                    parent_id=getattr(message.channel, "parent_id", None),
                    configured_channel_id=self._channel_id,
                )
                return

            channel = message.channel
            if isinstance(channel, discord.Thread):
                await self._handle_thread_message(channel, message)
                return
            if isinstance(channel, discord.TextChannel):
                await self._handle_channel_message(channel, message)

    async def _ensure_thread(
        self,
        channel: discord.TextChannel,
        message: discord.Message,
    ) -> discord.Thread:
        title = message.content[:80] if message.content else f"Run {message.id}"
        try:
            return await message.create_thread(name=title, auto_archive_duration=1440)
        except discord.HTTPException as error:
            if getattr(error, "code", 0) != _THREAD_ALREADY_EXISTS_CODE:
                raise
            logger.info(
                "discord_thread_already_exists",
                message_id=message.id,
                channel_id=channel.id,
            )
            existing = channel.get_thread(message.id)
            if existing is not None:
                return existing
            fetched = await channel.guild.fetch_channel(message.id)
            if not isinstance(fetched, discord.Thread):
                raise
            return fetched

    async def _handle_channel_message(
        self,
        channel: discord.TextChannel,
        message: discord.Message,
    ) -> None:
        thread = await self._ensure_thread(channel, message)
        await self._submit_and_reply(
            thread,
            author=message.author.display_name,
            content=message.content,
            resume_key=str(thread.id),
        )

    async def _handle_thread_message(
        self,
        thread: discord.Thread,
        message: discord.Message,
    ) -> None:
        await self._submit_and_reply(
            thread,
            author=message.author.display_name,
            content=message.content,
            resume_key=str(thread.id),
        )

    async def _submit_and_reply(
        self,
        thread: discord.Thread,
        *,
        author: str,
        content: str,
        resume_key: str,
    ) -> None:
        try:
            async with thread.typing():
                result = await self._run_service.submit_message(
                    resume_key=resume_key,
                    author=author,
                    content=content,
                )
        except Exception as error:
            logger.exception("discord_dispatch_failed")
            await self._send_chunked(thread, f"[error] {error}")
            return

        if result is None:
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
