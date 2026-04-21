import asyncio
from pathlib import Path

import structlog
import watchfiles

from agent_engine.application.integration.intake import Intake
from agent_engine.application.vault.service.vault_service import VaultService

logger = structlog.get_logger(__name__)

_DEBOUNCE_MS = 500
_STEP_MS = 100
_MARKDOWN_SUFFIXES = {".md", ".markdown"}


class VaultWatcher(Intake):

    def __init__(self, directory: Path, vault: VaultService) -> None:
        self._directory = directory
        self._vault = vault
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    @property
    def name(self) -> str:
        return "vault_watcher"

    async def start(self) -> None:
        if self._task is not None:
            return
        self._directory.mkdir(parents=True, exist_ok=True)
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        logger.info("vault_watcher_started", directory=str(self._directory))

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stop_event is not None
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
        self._stop_event = None
        logger.info("vault_watcher_stopped")

    async def _run(self) -> None:
        assert self._stop_event is not None
        try:
            async for changes in watchfiles.awatch(
                str(self._directory),
                debounce=_DEBOUNCE_MS,
                step=_STEP_MS,
                recursive=True,
                stop_event=self._stop_event,
            ):
                for change_type, path_str in changes:
                    await self._handle(change_type, Path(path_str))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("vault_watcher_crashed")

    async def _handle(self, change_type: watchfiles.Change, path: Path) -> None:
        if path.suffix.lower() not in _MARKDOWN_SUFFIXES:
            return
        if any(part.startswith(".") for part in path.parts):
            return
        loop = asyncio.get_running_loop()
        try:
            if change_type == watchfiles.Change.deleted:
                await loop.run_in_executor(None, self._vault.evict, path)
            else:
                await loop.run_in_executor(None, self._vault.ingest, path)
        except Exception:
            logger.exception(
                "vault_watcher_handle_failed",
                path=str(path),
                change=change_type.name,
            )
