import structlog
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk._errors import CLIConnectionError

logger = structlog.get_logger(__name__)


class ProcessManager:

    def __init__(self) -> None:
        self._active_clients: dict[str, ClaudeSDKClient] = {}
        self._interrupted_runs: set[str] = set()

    def register(self, run_id: str, client: ClaudeSDKClient) -> None:
        self._active_clients[run_id] = client

    def unregister(self, run_id: str) -> None:
        self._active_clients.pop(run_id, None)

    def has_collision(self, run_id: str) -> bool:
        return run_id in self._active_clients

    def is_running(self, run_id: str) -> bool:
        return run_id in self._active_clients

    def active_run_ids(self) -> set[str]:
        return set(self._active_clients.keys())

    async def interrupt(self, run_id: str) -> bool:
        client = self._active_clients.get(run_id)
        if client is None:
            return False
        try:
            await client.interrupt()
        except CLIConnectionError:
            logger.warning("interrupt_client_disconnected", run_id=run_id)
            return False
        self._interrupted_runs.add(run_id)
        return True

    def consume_interrupted(self, run_id: str) -> bool:
        if run_id in self._interrupted_runs:
            self._interrupted_runs.discard(run_id)
            return True
        return False
