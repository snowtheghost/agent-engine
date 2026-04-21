import asyncio

import pytest

from agent_engine.application.run.service.resume_handle_store import ResumeHandleStore
from agent_engine.application.run.service.run_service import RunService
from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.application.thread.service.thread_service import (
    AGENT_AUTHOR,
    ThreadService,
)
from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run_result import RunResult
from agent_engine.core.thread.model.thread import Thread


class InMemoryThreadRepository(ThreadRepository):

    def __init__(self) -> None:
        self.threads: dict[str, Thread] = {}

    def append(self, resume_key, entry):
        thread = self.threads.setdefault(resume_key, Thread(resume_key=resume_key))
        thread.entries.append(entry)

    def load(self, resume_key):
        return self.threads.get(resume_key)

    def delete(self, resume_key):
        return self.threads.pop(resume_key, None) is not None

    def list_keys(self):
        return list(self.threads.keys())

    def update_cursor(self, resume_key, cursor):
        thread = self.threads.setdefault(resume_key, Thread(resume_key=resume_key))
        thread.read_cursor = cursor


class InMemoryResumeStore(ResumeHandleStore):

    def __init__(self) -> None:
        self.storage: dict[str, ResumeHandle] = {}

    def get(self, resume_key):
        return self.storage.get(resume_key)

    def put(self, resume_key, handle):
        self.storage[resume_key] = handle

    def clear(self, resume_key):
        self.storage.pop(resume_key, None)


def _make_service(runner, resume_handles, thread_service=None):
    return RunService(
        runners={runner.provider_name: runner},
        default_provider=runner.provider_name,
        resume_handles=resume_handles,
        thread_service=thread_service,
    )


class FakeRunner:

    def __init__(self, session_ids: list[str] | None = None) -> None:
        self._session_ids = list(session_ids or ["sess-1"])
        self.calls: list[dict] = []
        self._active: set[str] = set()
        self._interrupted: set[str] = set()

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
        if run_id in self._active:
            self._active.discard(run_id)
            self._interrupted.add(run_id)
            return True
        return False

    def is_running(self, run_id):
        return run_id in self._active

    def active_run_ids(self):
        return set(self._active)


class SlowRunner:

    def __init__(self) -> None:
        self._active: dict[str, asyncio.Event] = {}
        self._interrupted: set[str] = set()
        self.calls: list[dict] = []
        self._run_started: dict[str, asyncio.Event] = {}

    @property
    def provider_name(self) -> str:
        return "slow"

    async def run(self, prompt, *, run_id, resume_handle, model):
        finish_event = asyncio.Event()
        start_event = asyncio.Event()
        self._active[run_id] = finish_event
        self._run_started[run_id] = start_event
        self.calls.append(
            {
                "prompt": prompt,
                "run_id": run_id,
                "resume_handle": resume_handle,
                "model": model,
            }
        )
        start_event.set()
        await finish_event.wait()
        self._active.pop(run_id, None)
        return RunResult(
            run_id=run_id,
            success=True,
            summary="ok",
            error=None,
            duration_ms=1,
            cost_usd=0.0,
            turns=1,
            resume_handle=ResumeHandle(provider="slow", session_id="sess-1"),
        )

    async def interrupt(self, run_id):
        event = self._active.get(run_id)
        if event is not None:
            self._interrupted.add(run_id)
            event.set()
            return True
        return False

    def is_running(self, run_id):
        return run_id in self._active

    def active_run_ids(self):
        return set(self._active.keys())

    def was_interrupted(self, run_id):
        return run_id in self._interrupted


@pytest.mark.asyncio
async def test_dispatch_first_call_no_resume_handle():
    store = InMemoryResumeStore()
    runner = FakeRunner()
    service = _make_service(runner, store)

    result = await service.dispatch("hi", resume_key="k1")
    assert result.success
    assert runner.calls[0]["resume_handle"] is None
    assert store.get("k1") is not None
    assert store.get("k1").session_id == "sess-1"


@pytest.mark.asyncio
async def test_dispatch_second_call_uses_stored_handle():
    store = InMemoryResumeStore()
    runner = FakeRunner(session_ids=["sess-1", "sess-2"])
    service = _make_service(runner, store)

    await service.dispatch("hi", resume_key="k1")
    await service.dispatch("again", resume_key="k1")

    assert runner.calls[1]["resume_handle"] is not None
    assert runner.calls[1]["resume_handle"].session_id == "sess-1"
    assert store.get("k1").session_id == "sess-2"


@pytest.mark.asyncio
async def test_dispatch_without_resume_key_does_not_persist():
    store = InMemoryResumeStore()
    runner = FakeRunner()
    service = _make_service(runner, store)

    await service.dispatch("hi")
    assert store.storage == {}


@pytest.mark.asyncio
async def test_clear_resume_removes_handle():
    store = InMemoryResumeStore()
    runner = FakeRunner()
    service = _make_service(runner, store)

    await service.dispatch("hi", resume_key="k1")
    service.clear_resume("k1")
    assert store.get("k1") is None


class TestInterrupt:
    @pytest.mark.asyncio
    async def test_interrupt_delegates_to_runner(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        runner._active.add("run-1")
        service = _make_service(runner, store)

        result = await service.interrupt("run-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_interrupt_returns_false_for_unknown_run(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        service = _make_service(runner, store)

        result = await service.interrupt("nonexistent")
        assert result is False

    def test_active_run_ids_delegates_to_runner(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        runner._active.update({"run-1", "run-2"})
        service = _make_service(runner, store)

        assert service.active_run_ids() == {"run-1", "run-2"}

    def test_is_running_delegates_to_runner(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        runner._active.add("run-1")
        service = _make_service(runner, store)

        assert service.is_running("run-1") is True
        assert service.is_running("run-2") is False


class TestDispatchInterruptsActiveRun:
    @pytest.mark.asyncio
    async def test_interrupts_active_run_before_dispatching_new(self) -> None:
        runner = SlowRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store)

        first_dispatch = asyncio.create_task(
            service.dispatch("first", resume_key="k1")
        )

        while not runner.calls:
            await asyncio.sleep(0.01)

        first_run_id = runner.calls[0]["run_id"]

        started_event = runner._run_started.get(first_run_id)
        assert started_event is not None
        await started_event.wait()

        assert runner.is_running(first_run_id)

        second_dispatch = asyncio.create_task(
            service.dispatch("second", resume_key="k1")
        )

        await first_dispatch

        while len(runner.calls) < 2:
            await asyncio.sleep(0.01)

        second_run_id = runner.calls[1]["run_id"]
        finish_event = runner._active.get(second_run_id)
        assert finish_event is not None
        finish_event.set()

        await second_dispatch

        assert runner.was_interrupted(first_run_id)
        assert not runner.was_interrupted(second_run_id)
        assert runner.calls[0]["prompt"] == "first"
        assert runner.calls[1]["prompt"] == "second"

    @pytest.mark.asyncio
    async def test_no_interrupt_when_no_active_run(self) -> None:
        runner = FakeRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store)

        await service.dispatch("first", resume_key="k1")
        await service.dispatch("second", resume_key="k1")

        assert len(runner.calls) == 2
        assert len(runner._interrupted) == 0

    @pytest.mark.asyncio
    async def test_dispatch_without_resume_key_does_not_track(self) -> None:
        runner = FakeRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store)

        await service.dispatch("a")
        await service.dispatch("b")

        assert len(runner.calls) == 2

    @pytest.mark.asyncio
    async def test_active_run_cleared_after_dispatch_completes(self) -> None:
        runner = FakeRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store)

        await service.dispatch("hi", resume_key="k1")
        assert "k1" not in service._active_by_key


class TestSubmitMessage:

    @pytest.mark.asyncio
    async def test_submit_message_runs_drainer_for_single_entry(self) -> None:
        repository = InMemoryThreadRepository()
        thread_service = ThreadService(repository)
        runner = FakeRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store, thread_service)

        result = await service.submit_message(
            resume_key="k1",
            author="alice",
            content="hello",
        )

        assert result is not None
        assert runner.calls[0]["prompt"].startswith("[From: alice]")
        thread = repository.load("k1")
        assert thread is not None
        assert thread.read_cursor == 1
        assert thread.entries[-1].author == AGENT_AUTHOR

    @pytest.mark.asyncio
    async def test_submit_message_while_active_returns_none_and_combines(self) -> None:
        repository = InMemoryThreadRepository()
        thread_service = ThreadService(repository)
        runner = SlowRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store, thread_service)

        first = asyncio.create_task(
            service.submit_message(resume_key="k1", author="alice", content="first")
        )

        while not runner.calls:
            await asyncio.sleep(0.01)

        first_run_id = runner.calls[0]["run_id"]
        await runner._run_started[first_run_id].wait()

        second = await service.submit_message(
            resume_key="k1", author="alice", content="second"
        )
        third = await service.submit_message(
            resume_key="k1", author="alice", content="third"
        )
        assert second is None
        assert third is None

        while len(runner.calls) < 2:
            await asyncio.sleep(0.01)

        second_run_id = runner.calls[1]["run_id"]
        runner._active[second_run_id].set()

        result = await first

        assert result is not None
        assert "first" in runner.calls[0]["prompt"]
        assert runner.calls[1]["prompt"].startswith(
            "[Queued messages while you were working:]"
        )
        assert "second" in runner.calls[1]["prompt"]
        assert "third" in runner.calls[1]["prompt"]
        assert runner.was_interrupted(first_run_id)

    @pytest.mark.asyncio
    async def test_submit_message_logs_agent_reply(self) -> None:
        repository = InMemoryThreadRepository()
        thread_service = ThreadService(repository)
        runner = FakeRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store, thread_service)

        await service.submit_message(resume_key="k1", author="alice", content="hi")

        thread = repository.load("k1")
        assert thread is not None
        agent_entries = [e for e in thread.entries if e.author == AGENT_AUTHOR]
        assert len(agent_entries) == 1
        assert agent_entries[0].content == "ok"

    @pytest.mark.asyncio
    async def test_dispatch_routes_through_submit_message_when_thread_service_present(
        self,
    ) -> None:
        repository = InMemoryThreadRepository()
        thread_service = ThreadService(repository)
        runner = FakeRunner()
        store = InMemoryResumeStore()
        service = _make_service(runner, store, thread_service)

        result = await service.dispatch("hello", resume_key="k1")
        assert result is not None
        thread = repository.load("k1")
        assert thread is not None
        assert thread.entries[0].author == "integration"

    @pytest.mark.asyncio
    async def test_submit_message_without_thread_service_raises(self) -> None:
        store = InMemoryResumeStore()
        runner = FakeRunner()
        service = _make_service(runner, store)
        with pytest.raises(RuntimeError):
            await service.submit_message(
                resume_key="k1", author="alice", content="hi"
            )
