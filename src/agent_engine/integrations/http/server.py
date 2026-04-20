import asyncio

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent_engine.application.integration.intake import Intake
from agent_engine.application.run.service.run_service import RunService
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


class VaultSearchResponse(BaseModel):
    query: str
    results: list[dict]


class VaultEntryPayload(BaseModel):
    kind: str
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)


def build_app(run_service: RunService, vault: VaultService) -> FastAPI:
    app = FastAPI(title="Agent Engine", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "active_runs": sorted(run_service.active_run_ids()),
            "vault_entries": vault.count(),
        }

    @app.post("/runs", response_model=DispatchResponse)
    async def create_run(request: DispatchRequest) -> DispatchResponse:
        result = await run_service.dispatch(
            request.prompt,
            resume_key=request.resume_key,
            model=request.model,
        )
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

    @app.post("/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict[str, bool]:
        return {"cancelled": await run_service.interrupt(run_id)}

    @app.get("/runs")
    async def list_active_runs() -> dict[str, list[str]]:
        return {"active": sorted(run_service.active_run_ids())}

    @app.get("/vault/search", response_model=VaultSearchResponse)
    async def vault_search(q: str, limit: int = 5) -> VaultSearchResponse:
        hits = vault.search(q, limit)
        return VaultSearchResponse(
            query=q,
            results=[
                {
                    "entry_id": hit.entry.entry_id,
                    "kind": hit.entry.kind,
                    "title": hit.entry.title,
                    "tags": list(hit.entry.tags),
                    "body": hit.entry.body,
                    "created_at": hit.entry.created_at.isoformat(),
                    "score": hit.score,
                    "path": str(hit.path),
                }
                for hit in hits
            ],
        )

    @app.get("/vault/entries/{entry_id}")
    async def vault_recall(entry_id: str) -> dict:
        entry = vault.recall(entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="entry not found")
        return {
            "entry_id": entry.entry_id,
            "kind": entry.kind,
            "title": entry.title,
            "tags": list(entry.tags),
            "body": entry.body,
            "created_at": entry.created_at.isoformat(),
        }

    @app.post("/vault/entries")
    async def vault_create(payload: VaultEntryPayload) -> dict:
        entry = vault.write(
            kind=payload.kind,
            title=payload.title,
            body=payload.body,
            tags=tuple(payload.tags),
        )
        return {"entry_id": entry.entry_id}

    return app


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
            except asyncio.TimeoutError:
                logger.warning("http_intake_stop_timeout")
                self._task.cancel()
        logger.info("http_intake_stopped")
