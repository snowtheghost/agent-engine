from unittest.mock import AsyncMock

import pytest

from agent_engine.providers.claude.process_manager import ProcessManager


@pytest.fixture()
def manager() -> ProcessManager:
    return ProcessManager()


def _fake_client() -> AsyncMock:
    client = AsyncMock()
    client.interrupt = AsyncMock()
    return client


class TestRegister:
    def test_run_appears_as_active(self, manager: ProcessManager) -> None:
        client = _fake_client()
        manager.register("run-1", client)
        assert manager.is_running("run-1")
        assert "run-1" in manager.active_run_ids()

    def test_multiple_runs_tracked(self, manager: ProcessManager) -> None:
        manager.register("run-1", _fake_client())
        manager.register("run-2", _fake_client())
        assert manager.active_run_ids() == {"run-1", "run-2"}

    def test_re_register_replaces_client(self, manager: ProcessManager) -> None:
        old = _fake_client()
        new = _fake_client()
        manager.register("run-1", old)
        manager.register("run-1", new)
        assert manager.is_running("run-1")
        assert manager.active_run_ids() == {"run-1"}


class TestUnregister:
    def test_removes_active_run(self, manager: ProcessManager) -> None:
        manager.register("run-1", _fake_client())
        manager.unregister("run-1")
        assert not manager.is_running("run-1")
        assert "run-1" not in manager.active_run_ids()

    def test_unregister_unknown_is_noop(self, manager: ProcessManager) -> None:
        manager.unregister("nonexistent")


class TestHasCollision:
    def test_true_when_active(self, manager: ProcessManager) -> None:
        manager.register("run-1", _fake_client())
        assert manager.has_collision("run-1") is True

    def test_false_when_not_registered(self, manager: ProcessManager) -> None:
        assert manager.has_collision("run-1") is False

    def test_false_after_unregister(self, manager: ProcessManager) -> None:
        manager.register("run-1", _fake_client())
        manager.unregister("run-1")
        assert manager.has_collision("run-1") is False


class TestInterrupt:
    @pytest.mark.asyncio
    async def test_interrupts_active_client(self, manager: ProcessManager) -> None:
        client = _fake_client()
        manager.register("run-1", client)

        result = await manager.interrupt("run-1")

        assert result is True
        client.interrupt.assert_awaited_once()
        assert manager.consume_interrupted("run-1") is True

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_run(self, manager: ProcessManager) -> None:
        result = await manager.interrupt("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_unregistered_run(self, manager: ProcessManager) -> None:
        client = _fake_client()
        manager.register("run-1", client)
        manager.unregister("run-1")

        result = await manager.interrupt("run-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self, manager: ProcessManager) -> None:
        from claude_agent_sdk._errors import CLIConnectionError

        client = _fake_client()
        client.interrupt.side_effect = CLIConnectionError("disconnected")
        manager.register("run-1", client)

        result = await manager.interrupt("run-1")

        assert result is False
        assert manager.consume_interrupted("run-1") is False


class TestConsumeInterrupted:
    @pytest.mark.asyncio
    async def test_clears_flag_after_consume(self, manager: ProcessManager) -> None:
        client = _fake_client()
        manager.register("run-1", client)
        await manager.interrupt("run-1")

        assert manager.consume_interrupted("run-1") is True
        assert manager.consume_interrupted("run-1") is False

    def test_returns_false_when_not_interrupted(self, manager: ProcessManager) -> None:
        assert manager.consume_interrupted("run-1") is False

    @pytest.mark.asyncio
    async def test_does_not_unregister_client(self, manager: ProcessManager) -> None:
        client = _fake_client()
        manager.register("run-1", client)
        await manager.interrupt("run-1")
        manager.consume_interrupted("run-1")

        assert manager.is_running("run-1")
