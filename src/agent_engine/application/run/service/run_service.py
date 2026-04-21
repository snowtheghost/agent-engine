import asyncio
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

import structlog

from agent_engine.application.run.runner.runner import Runner
from agent_engine.application.run.service.resume_handle_store import ResumeHandleStore
from agent_engine.application.thread.service.thread_service import ThreadService
from agent_engine.core.run.model.run_result import RunResult
from agent_engine.core.thread.model.thread import AttachmentMetadata, ThreadEntry

logger = structlog.get_logger(__name__)

_INTERRUPT_WAIT_TIMEOUT = 30
INTEGRATION_AUTHOR = "integration"


class RunService:

    def __init__(
        self,
        runner: Runner,
        resume_handles: ResumeHandleStore,
        thread_service: ThreadService | None = None,
    ) -> None:
        self._runner = runner
        self._resume_handles = resume_handles
        self._thread_service = thread_service
        self._active_by_key: dict[str, str] = {}
        self._drainer_active_keys: set[str] = set()

    async def dispatch(
        self,
        prompt: str,
        *,
        resume_key: str | None = None,
        model: str | None = None,
    ) -> RunResult | None:
        if resume_key is not None and self._thread_service is not None:
            return await self.submit_message(
                resume_key=resume_key,
                author=INTEGRATION_AUTHOR,
                content=prompt,
                model=model,
            )
        return await self._execute(prompt, resume_key=resume_key, model=model)

    async def submit_message(
        self,
        *,
        resume_key: str,
        author: str,
        content: str,
        attachments: Iterable[AttachmentMetadata] = (),
        model: str | None = None,
    ) -> RunResult | None:
        if self._thread_service is None:
            raise RuntimeError("submit_message requires a configured ThreadService")

        entry = ThreadEntry(
            author=author,
            content=content,
            attachments=tuple(attachments),
            timestamp=datetime.now(UTC),
        )
        self._thread_service.handle_message(resume_key, entry)

        if resume_key in self._drainer_active_keys:
            await self._signal_interrupt(resume_key)
            return None

        self._drainer_active_keys.add(resume_key)
        try:
            return await self._drain(resume_key, model)
        finally:
            self._drainer_active_keys.discard(resume_key)

    async def _drain(self, resume_key: str, model: str | None) -> RunResult | None:
        if self._thread_service is None:
            return None
        last_result: RunResult | None = None
        while True:
            pending = self._thread_service.get_pending_prompts(resume_key)
            if pending is None:
                return last_result
            prompt, cursor = pending
            last_result = await self._execute(prompt, resume_key=resume_key, model=model)
            if last_result.summary:
                self._thread_service.log_reply(resume_key, last_result.summary)
            self._thread_service.acknowledge(resume_key, cursor)

    async def _execute(
        self,
        prompt: str,
        *,
        resume_key: str | None,
        model: str | None,
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
            started_at=datetime.now(UTC).isoformat(),
        )

        if resume_key is not None and resume_key not in self._drainer_active_keys:
            await self._interrupt_active_run(resume_key)
        if resume_key is not None:
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

    async def _signal_interrupt(self, resume_key: str) -> None:
        active_run_id = self._active_by_key.get(resume_key)
        if active_run_id is None:
            return
        if not self._runner.is_running(active_run_id):
            return
        logger.info(
            "signalling_interrupt",
            resume_key=resume_key,
            run_id=active_run_id,
        )
        await self._runner.interrupt(active_run_id)

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
