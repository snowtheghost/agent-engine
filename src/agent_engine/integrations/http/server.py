import asyncio

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent_engine.application.integration.intake import Intake
from agent_engine.application.run.service.run_service import RunService
from agent_engine.application.thread.service.thread_service import ThreadService
from agent_engine.application.vault.service.vault_service import VaultService

logger = structlog.get_logger(__name__)


class DispatchRequest(BaseModel):
    prompt: str
    resume_key: str | None = None
    model: str | None = None


class DispatchResponse(BaseModel):
    run_id: str
    success: bool
    summary: str
    error: str | None
    duration_ms: int
    cost_usd: float
    turns: int
    resume_provider: str | None
    resume_session_id: str | None


class ThreadMessageRequest(BaseModel):
    author: str
    content: str


class VaultSearchResponse(BaseModel):
    query: str
    results: list[dict]


class VaultEntryPayload(BaseModel):
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    subdirectory: str | None = None


def build_app(
    run_service: RunService,
    vault: VaultService,
    thread_service: ThreadService | None = None,
) -> FastAPI:
    app = FastAPI(title="Agent Engine", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "active_runs": sorted(run_service.active_run_ids()),
            "vault_chunks": vault.count(),
        }

    @app.post("/runs", response_model=DispatchResponse | None)
    async def create_run(request: DispatchRequest) -> DispatchResponse | None:
        result = await run_service.dispatch(
            request.prompt,
            resume_key=request.resume_key,
            model=request.model,
        )
        if result is None:
            return None
        return _dispatch_response(result)

    @app.post("/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict[str, bool]:
        return {"cancelled": await run_service.interrupt(run_id)}

    @app.get("/runs")
    async def list_active_runs() -> dict[str, list[str]]:
        return {"active": sorted(run_service.active_run_ids())}

    @app.post(
        "/threads/{resume_key}/messages",
        response_model=DispatchResponse | None,
    )
    async def submit_thread_message(
        resume_key: str,
        request: ThreadMessageRequest,
    ) -> DispatchResponse | None:
        if thread_service is None:
            raise HTTPException(status_code=404, detail="threads not configured")
        result = await run_service.submit_message(
            resume_key=resume_key,
            author=request.author,
            content=request.content,
        )
        if result is None:
            return None
        return _dispatch_response(result)

    @app.get("/threads")
    async def list_threads() -> dict[str, list[dict]]:
        if thread_service is None:
            raise HTTPException(status_code=404, detail="threads not configured")
        summaries: list[dict] = []
        for key in thread_service.list_threads():
            thread = thread_service.get_thread(key)
            if thread is None:
                continue
            last_timestamp = (
                thread.entries[-1].timestamp.isoformat() if thread.entries else None
            )
            summaries.append(
                {
                    "resume_key": thread.resume_key,
                    "entry_count": len(thread.entries),
                    "last_timestamp": last_timestamp,
                }
            )
        return {"threads": summaries}

    @app.get("/threads/{resume_key}")
    async def get_thread(resume_key: str) -> dict:
        if thread_service is None:
            raise HTTPException(status_code=404, detail="threads not configured")
        thread = thread_service.get_thread(resume_key)
        if thread is None:
            raise HTTPException(status_code=404, detail="thread not found")
        return {
            "resume_key": thread.resume_key,
            "read_cursor": thread.read_cursor,
            "entries": [
                {
                    "author": entry.author,
                    "content": entry.content,
                    "timestamp": entry.timestamp.isoformat(),
                    "attachments": [
                        {
                            "path": attachment.path,
                            "filename": attachment.filename,
                            "content_type": attachment.content_type,
                            "size": attachment.size,
                            "description": attachment.description,
                        }
                        for attachment in entry.attachments
                    ],
                }
                for entry in thread.entries
            ],
        }

    @app.get("/vault/search", response_model=VaultSearchResponse)
    async def vault_search(q: str, limit: int = 5, file: str | None = None) -> VaultSearchResponse:
        hits = vault.search(q, limit, file_filter=file)
        return VaultSearchResponse(
            query=q,
            results=[
                {
                    "chunk_id": hit.chunk.chunk_id,
                    "file_path": hit.chunk.file_path,
                    "heading": hit.chunk.heading,
                    "content": hit.chunk.content,
                    "tags": list(hit.chunk.tags),
                    "score": hit.score,
                    "path": str(hit.path),
                }
                for hit in hits
            ],
        )

    @app.get("/vault/recall")
    async def vault_recall(path: str) -> dict:
        body = vault.recall(path)
        if body is None:
            raise HTTPException(status_code=404, detail="file not found")
        return {"path": path, "body": body}

    @app.post("/vault/entries")
    async def vault_create(payload: VaultEntryPayload) -> dict:
        written = vault.write(
            title=payload.title,
            content=payload.content,
            tags=tuple(payload.tags),
            subdirectory=payload.subdirectory,
        )
        return {"path": str(written)}

    return app


def _dispatch_response(result) -> DispatchResponse:
    handle = result.resume_handle
    return DispatchResponse(
        run_id=result.run_id,
        success=result.success,
        summary=result.summary,
        error=result.error,
        duration_ms=result.duration_ms,
        cost_usd=result.cost_usd,
        turns=result.turns,
        resume_provider=handle.provider if handle else None,
        resume_session_id=handle.session_id if handle else None,
    )


class HttpIntake(Intake):

    def __init__(
        self,
        app: FastAPI,
        host: str,
        port: int,
    ) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        return "http"

    async def start(self) -> None:
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="info",
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        logger.info("http_intake_started", host=self._host, port=self._port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except TimeoutError:
                logger.warning("http_intake_stop_timeout")
                self._task.cancel()
        logger.info("http_intake_stopped")
