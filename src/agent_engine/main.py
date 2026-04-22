import asyncio
import signal
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import structlog

from agent_engine.application.indexing.indexer import AsyncIndexingWorker
from agent_engine.application.integration.intake import Intake
from agent_engine.application.run.runner.runner import Runner
from agent_engine.application.run.service.run_service import RunService
from agent_engine.application.thread.index.thread_index import ThreadIndex
from agent_engine.application.thread.scanner.thread_scanner import ThreadScanner
from agent_engine.application.thread.service.thread_service import ThreadService
from agent_engine.application.vault.scanner.vault_scanner import VaultScanner
from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.infrastructure.persistence.database import open_database
from agent_engine.infrastructure.persistence.sqlite_resume_handle_store import (
    SqliteResumeHandleStore,
)
from agent_engine.infrastructure.persistence.sqlite_thread_cursor_store import (
    SqliteThreadCursorStore,
)
from agent_engine.infrastructure.system.config.config import EngineConfig, load_config
from agent_engine.infrastructure.system.logging.logging import configure_logging
from agent_engine.infrastructure.thread.indexing_thread_repository import (
    IndexingThreadRepository,
)
from agent_engine.infrastructure.thread.jsonl_thread_scanner import JsonlThreadScanner
from agent_engine.infrastructure.thread.persistence.jsonl_thread_repository import (
    JsonlThreadRepository,
)
from agent_engine.infrastructure.vault.file_vault_scanner import FileVaultScanner
from agent_engine.integrations.discord.bot import DiscordIntake
from agent_engine.integrations.http.server import HttpIntake, build_app
from agent_engine.integrations.skills.installer import install_bundled_skills
from agent_engine.integrations.watcher.vault_watcher import VaultWatcher
from agent_engine.providers.claude.runner import ClaudeCodeRunner
from agent_engine.tools.thread_tools import build_thread_mcp_server
from agent_engine.tools.vault_tools import build_vault_mcp_server

logger = structlog.get_logger(__name__)


@dataclass
class Engine:
    config: EngineConfig
    connection: sqlite3.Connection
    run_service: RunService
    vault_service: VaultService
    vault_scanner: VaultScanner
    thread_service: ThreadService
    thread_index: ThreadIndex
    thread_scanner: ThreadScanner
    indexing_worker: AsyncIndexingWorker
    intakes: list[Intake]


def _build_vault(
    config: EngineConfig,
    worker: AsyncIndexingWorker,
) -> tuple[VaultService, VaultScanner]:
    from agent_engine.infrastructure.vault.embedding import (
        EMBEDDING_DIM,
        embed_documents,
        embed_queries,
    )
    from agent_engine.infrastructure.vault.numpy_vault_index import NumpyVaultIndex
    from agent_engine.infrastructure.vault.numpy_vector_store import NumpyVectorStore

    store_dir = config.data_dir / ".store"
    store = NumpyVectorStore(
        store_dir=store_dir,
        name="vault",
        embed_fn=embed_documents,
        embedding_dim=EMBEDDING_DIM,
        query_embed_fn=embed_queries,
    )
    index = NumpyVaultIndex(store=store)
    scanner = FileVaultScanner(
        directory=config.vault.directory,
        index=index,
    )
    service = VaultService(
        directory=config.vault.directory,
        index=index,
        scanner=scanner,
        scheduler=worker,
    )
    return service, scanner


def _build_thread(
    config: EngineConfig,
    connection: sqlite3.Connection,
    worker: AsyncIndexingWorker,
) -> tuple[ThreadService, ThreadIndex, ThreadScanner]:
    from agent_engine.infrastructure.thread.numpy_thread_index import NumpyThreadIndex
    from agent_engine.infrastructure.vault.embedding import (
        EMBEDDING_DIM,
        embed_documents,
        embed_queries,
    )
    from agent_engine.infrastructure.vault.numpy_vector_store import NumpyVectorStore

    store = NumpyVectorStore(
        store_dir=config.data_dir / ".store",
        name="thread",
        embed_fn=embed_documents,
        embedding_dim=EMBEDDING_DIM,
        query_embed_fn=embed_queries,
    )
    thread_index = NumpyThreadIndex(store=store)

    cursor_store = SqliteThreadCursorStore(connection)
    base_repository = JsonlThreadRepository(
        data_dir=config.data_dir,
        cursor_store=cursor_store,
    )
    repository = IndexingThreadRepository(
        inner=base_repository,
        index=thread_index,
        scheduler=worker,
    )
    thread_service = ThreadService(repository=repository)

    thread_scanner = JsonlThreadScanner(
        threads_dir=config.data_dir / "threads",
        repository=base_repository,
        index=thread_index,
    )
    return thread_service, thread_index, thread_scanner


def _build_runners(
    config: EngineConfig,
    vault_service: VaultService,
    thread_service: ThreadService,
    thread_index: ThreadIndex,
) -> dict[str, Runner]:
    mcp_servers = {
        "vault": build_vault_mcp_server(vault_service),
        "thread": build_thread_mcp_server(thread_service, index=thread_index),
    }
    runners: dict[str, Runner] = {}
    if config.providers.claude is not None:
        runners["claude"] = ClaudeCodeRunner(
            cwd=str(config.cwd),
            model=config.providers.claude.model,
            effort=config.providers.claude.effort,
            mcp_servers=mcp_servers,
            timezone=config.timezone,
        )
    if not runners:
        raise ValueError("no providers configured; at least one is required")
    return runners


def build_engine(cwd: Path, data_dir: Path | None = None) -> Engine:
    config = load_config(cwd, data_dir=data_dir)
    configure_logging(config.log_level)
    config.data_dir.mkdir(parents=True, exist_ok=True)

    connection = open_database(config.database_path)
    indexing_worker = AsyncIndexingWorker()
    vault_service, vault_scanner = _build_vault(config, indexing_worker)
    vault_scanner.scan()
    installed = install_bundled_skills(config.cwd)
    logger.info("skills_installed", skills=installed, count=len(installed))

    thread_service, thread_index, thread_scanner = _build_thread(
        config, connection, indexing_worker
    )
    thread_scanner.scan()

    runners = _build_runners(config, vault_service, thread_service, thread_index)
    resume_store = SqliteResumeHandleStore(connection)
    run_service = RunService(
        runners=runners,
        default_provider=config.default_provider,
        resume_handles=resume_store,
        thread_service=thread_service,
    )

    logger.info(
        "engine_built",
        cwd=str(config.cwd),
        providers=sorted(runners.keys()),
        default_provider=config.default_provider,
    )
    return Engine(
        config=config,
        connection=connection,
        run_service=run_service,
        vault_service=vault_service,
        vault_scanner=vault_scanner,
        thread_service=thread_service,
        thread_index=thread_index,
        thread_scanner=thread_scanner,
        indexing_worker=indexing_worker,
        intakes=[],
    )


def shutdown_engine(engine: Engine) -> None:
    try:
        engine.connection.close()
    except Exception:
        logger.exception("connection_close_failed")


def _build_intakes(
    engine: Engine,
    *,
    disable_discord: bool,
    disable_http: bool,
    disable_watcher: bool,
) -> list[Intake]:
    intakes: list[Intake] = []

    if not disable_watcher:
        intakes.append(
            VaultWatcher(
                directory=engine.config.vault.directory,
                vault=engine.vault_service,
            )
        )

    if not disable_http and engine.config.http.enabled:
        app = build_app(engine.run_service, engine.vault_service, engine.thread_service)
        intakes.append(
            HttpIntake(app=app, host=engine.config.http.host, port=engine.config.http.port)
        )

    if not disable_discord:
        discord_config = engine.config.discord
        if discord_config.token and discord_config.channel_id is not None:
            intakes.append(
                DiscordIntake(
                    token=discord_config.token,
                    channel_id=discord_config.channel_id,
                    run_service=engine.run_service,
                    character_limit=discord_config.character_limit,
                )
            )
        elif not discord_config.token:
            logger.info("discord_intake_skipped_no_token")
        else:
            logger.info("discord_intake_skipped_no_channel_id")

    return intakes


async def run_engine(
    cwd: Path,
    data_dir: Path | None = None,
    *,
    disable_discord: bool = False,
    disable_http: bool = False,
    disable_watcher: bool = False,
) -> None:
    engine = build_engine(cwd, data_dir=data_dir)
    engine.intakes = _build_intakes(
        engine,
        disable_discord=disable_discord,
        disable_http=disable_http,
        disable_watcher=disable_watcher,
    )

    stop_event = asyncio.Event()

    def _on_signal(*_: object) -> None:
        logger.info("engine_shutdown_signal_received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            pass

    await engine.indexing_worker.start()

    for intake in engine.intakes:
        await intake.start()
        logger.info("intake_started", intake=intake.name)

    logger.info("engine_running", intakes=[i.name for i in engine.intakes])

    try:
        await stop_event.wait()
    finally:
        for intake in reversed(engine.intakes):
            try:
                await intake.stop()
            except Exception:
                logger.exception("intake_stop_failed", intake=intake.name)
        try:
            await engine.indexing_worker.stop()
        except Exception:
            logger.exception("indexing_worker_stop_failed")
        shutdown_engine(engine)
        logger.info("engine_stopped")


if __name__ == "__main__":
    import sys

    from agent_engine.integrations.cli.main import main

    sys.exit(main())
