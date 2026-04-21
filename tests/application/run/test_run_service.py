import pytest

from agent_engine.application.run.service.resume_handle_store import ResumeHandleStore
from agent_engine.application.run.service.run_service import RunService
from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run_result import RunResult


class InMemoryResumeStore(ResumeHandleStore):

    def __init__(self) -> None:
        self.storage: dict[str, ResumeHandle] = {}

    def get(self, resume_key):
        return self.storage.get(resume_key)

    def put(self, resume_key, handle):
        self.storage[resume_key] = handle

    def clear(self, resume_key):
        self.storage.pop(resume_key, None)


class FakeRunner:

    def __init__(self, session_ids: list[str] | None = None) -> None:
        self._session_ids = list(session_ids or ["sess-1"])
        self.calls: list[dict] = []
        self._active: set[str] = set()

    @property
    def provider_name(self) -> str:
        return "fake"

    async def run(self, prompt, *, run_id, resume_handle, model):
        self.calls.append(
            {
                "prompt": prompt,
                "run_id": run_id,
                "resume_handle": resume_handle,
                "model": model,
            }
        )
        session_id = self._session_ids[min(len(self.calls) - 1, len(self._session_ids) - 1)]
        return RunResult(
            run_id=run_id,
            success=True,
            summary="ok",
            error=None,
            duration_ms=1,
            cost_usd=0.0,
            turns=1,
            resume_handle=ResumeHandle(provider="fake", session_id=session_id),
        )

    async def interrupt(self, run_id):
        return run_id in self._active

    def is_running(self, run_id):
        return run_id in self._active

    def active_run_ids(self):
        return set(self._active)


@pytest.mark.asyncio
async def test_dispatch_first_call_no_resume_handle():
    store = InMemoryResumeStore()
    runner = FakeRunner()
    service = RunService(runner=runner, resume_handles=store)

    result = await service.dispatch("hi", resume_key="k1")
    assert result.success
    assert runner.calls[0]["resume_handle"] is None
    assert store.get("k1") is not None
    assert store.get("k1").session_id == "sess-1"


@pytest.mark.asyncio
async def test_dispatch_second_call_uses_stored_handle():
    store = InMemoryResumeStore()
    runner = FakeRunner(session_ids=["sess-1", "sess-2"])
    service = RunService(runner=runner, resume_handles=store)

    await service.dispatch("hi", resume_key="k1")
    await service.dispatch("again", resume_key="k1")

    assert runner.calls[1]["resume_handle"] is not None
    assert runner.calls[1]["resume_handle"].session_id == "sess-1"
    assert store.get("k1").session_id == "sess-2"


@pytest.mark.asyncio
async def test_dispatch_without_resume_key_does_not_persist():
    store = InMemoryResumeStore()
    runner = FakeRunner()
    service = RunService(runner=runner, resume_handles=store)

    await service.dispatch("hi")
    assert store.storage == {}


@pytest.mark.asyncio
async def test_clear_resume_removes_handle():
    store = InMemoryResumeStore()
    runner = FakeRunner()
    service = RunService(runner=runner, resume_handles=store)

    await service.dispatch("hi", resume_key="k1")
    service.clear_resume("k1")
    assert store.get("k1") is None


class TestInterrupt:
    @pytest.mark.asyncio
    async def test_interrupt_delegates_to_runner(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        runner._active.add("run-1")
        service = RunService(runner=runner, resume_handles=store)

        result = await service.interrupt("run-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_interrupt_returns_false_for_unknown_run(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        service = RunService(runner=runner, resume_handles=store)

        result = await service.interrupt("nonexistent")
        assert result is False

    def test_active_run_ids_delegates_to_runner(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        runner._active.update({"run-1", "run-2"})
        service = RunService(runner=runner, resume_handles=store)

        assert service.active_run_ids() == {"run-1", "run-2"}

    def test_is_running_delegates_to_runner(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        runner._active.add("run-1")
        service = RunService(runner=runner, resume_handles=store)

        assert service.is_running("run-1") is True
        assert service.is_running("run-2") is False
