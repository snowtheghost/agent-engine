import asyncio
import uuid
from datetime import datetime, timezone

import structlog

from agent_engine.application.run.runner.runner import Runner
from agent_engine.application.run.service.resume_handle_store import ResumeHandleStore
from agent_engine.core.run.model.run_result import RunResult

logger = structlog.get_logger(__name__)

_INTERRUPT_WAIT_TIMEOUT = 30


class RunService:

    def __init__(
        self,
        runner: Runner,
        resume_handles: ResumeHandleStore,
    ) -> None:
        self._runner = runner
        self._resume_handles = resume_handles
        self._active_by_key: dict[str, str] = {}

    async def dispatch(
        self,
        prompt: str,
        *,
        resume_key: str | None = None,
        model: str | None = None,
    ) -> RunResult:
        run_id = str(uuid.uuid4())
        existing_handle = (
            self._resume_handles.get(resume_key) if resume_key is not None else None
        )

        logger.info(
            "run_dispatch",
            run_id=run_id,
            resume_key=resume_key,
            resuming=existing_handle is not None,
            provider=self._runner.provider_name,
            model=model,
            prompt_preview=prompt[:120],
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        if resume_key is not None:
            await self._interrupt_active_run(resume_key)
            self._active_by_key[resume_key] = run_id

        try:
            result = await self._runner.run(
                prompt,
                run_id=run_id,
                resume_handle=existing_handle,
                model=model,
            )
        finally:
            if resume_key is not None:
                self._active_by_key.pop(resume_key, None)

        if resume_key is not None and result.resume_handle is not None:
            self._resume_handles.put(resume_key, result.resume_handle)

        logger.info(
            "run_completed",
            run_id=run_id,
            resume_key=resume_key,
            success=result.success,
            duration_ms=result.duration_ms,
            cost_usd=result.cost_usd,
            turns=result.turns,
        )
        return result

    async def _interrupt_active_run(self, resume_key: str) -> None:
        active_run_id = self._active_by_key.get(resume_key)
        if active_run_id is None:
            return
        if not self._runner.is_running(active_run_id):
            self._active_by_key.pop(resume_key, None)
            return

        logger.info(
            "interrupting_active_run",
            resume_key=resume_key,
            run_id=active_run_id,
        )
        await self._runner.interrupt(active_run_id)

        deadline = asyncio.get_running_loop().time() + _INTERRUPT_WAIT_TIMEOUT
        while self._runner.is_running(active_run_id):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning(
                    "interrupt_wait_timeout",
                    resume_key=resume_key,
                    run_id=active_run_id,
                )
                break
            await asyncio.sleep(0.1)

        self._active_by_key.pop(resume_key, None)

    async def interrupt(self, run_id: str) -> bool:
        return await self._runner.interrupt(run_id)

    def active_run_ids(self) -> set[str]:
        return self._runner.active_run_ids()

    def is_running(self, run_id: str) -> bool:
        return self._runner.is_running(run_id)

    def clear_resume(self, resume_key: str) -> None:
        self._resume_handles.clear(resume_key)
