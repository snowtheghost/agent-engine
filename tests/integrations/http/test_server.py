import pytest
from fastapi.testclient import TestClient

from agent_engine.application.run.service.resume_handle_store import ResumeHandleStore
from agent_engine.application.run.service.run_service import RunService
from agent_engine.application.thread.repository.thread_repository import ThreadRepository
from agent_engine.application.thread.service.thread_service import ThreadService
from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run_result import RunResult
from agent_engine.core.thread.model.thread import Thread
from agent_engine.infrastructure.vault.file_vault_scanner import FileVaultScanner
from agent_engine.infrastructure.vault.in_memory_vault_index import InMemoryVaultIndex
from agent_engine.integrations.http.server import build_app


class InMemoryStore(ResumeHandleStore):

    def __init__(self) -> None:
        self.data: dict[str, ResumeHandle] = {}

    def get(self, k):
        return self.data.get(k)

    def put(self, k, h):
        self.data[k] = h

    def clear(self, k):
        self.data.pop(k, None)


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


class StubRunner:

    @property
    def provider_name(self):
        return "stub"

    async def run(self, prompt, *, run_id, resume_handle, model):
        return RunResult(
            run_id=run_id,
            success=True,
            summary=f"echo: {prompt}",
            error=None,
            duration_ms=1,
            cost_usd=0.0,
            turns=1,
            resume_handle=ResumeHandle(provider="stub", session_id="sess-1"),
        )

    async def interrupt(self, run_id):
        return False

    def is_running(self, run_id):
        return False

    def active_run_ids(self):
        return set()


@pytest.fixture()
def client(tmp_path):
    directory = tmp_path / "vault"
    directory.mkdir()
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=directory, index=index)
    vault = VaultService(directory=directory, index=index, scanner=scanner)
    thread_repository = InMemoryThreadRepository()
    thread_service = ThreadService(repository=thread_repository)
    stub_runner = StubRunner()
    run_service = RunService(
        runners={stub_runner.provider_name: stub_runner},
        default_provider=stub_runner.provider_name,
        resume_handles=InMemoryStore(),
        thread_service=thread_service,
    )
    app = build_app(run_service, vault, thread_service)
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["active_runs"] == []
    assert body["vault_chunks"] == 0


def test_post_runs_returns_summary(client):
    resp = client.post("/runs", json={"prompt": "hello", "resume_key": "k1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "hello" in body["summary"]
    assert body["resume_provider"] == "stub"
    assert body["resume_session_id"] == "sess-1"


def test_post_runs_without_resume_key_bypasses_thread(client):
    resp = client.post("/runs", json={"prompt": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == "echo: hello"


def test_vault_roundtrip(client):
    create = client.post(
        "/vault/entries",
        json={
            "title": "OAuth",
            "content": "PKCE flow details long enough to chunk.",
            "tags": ["auth"],
        },
    )
    assert create.status_code == 200
    created_path = create.json()["path"]
    assert created_path.endswith(".md")

    search = client.get("/vault/search", params={"q": "PKCE"})
    assert search.status_code == 200
    body = search.json()
    assert body["results"]
    assert body["results"][0]["file_path"].endswith(".md")

    recall = client.get("/vault/recall", params={"path": body["results"][0]["file_path"]})
    assert recall.status_code == 200
    assert "OAuth" in recall.json()["body"]


def test_vault_recall_not_found(client):
    resp = client.get("/vault/recall", params={"path": "missing.md"})
    assert resp.status_code == 404


def test_cancel_run_returns_false_for_unknown(client):
    resp = client.post("/runs/nonexistent/cancel")
    assert resp.status_code == 200
    assert resp.json() == {"cancelled": False}


def test_list_active_runs_returns_empty(client):
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == {"active": []}


class TrackableRunner:

    def __init__(self) -> None:
        self._active: set[str] = set()
        self._interrupted: set[str] = set()

    @property
    def provider_name(self):
        return "trackable"

    async def run(self, prompt, *, run_id, resume_handle, model):
        return RunResult(
            run_id=run_id,
            success=True,
            summary=f"echo: {prompt}",
            error=None,
            duration_ms=1,
            cost_usd=0.0,
            turns=1,
            resume_handle=ResumeHandle(provider="trackable", session_id="sess-1"),
        )

    async def interrupt(self, run_id):
        if run_id not in self._active:
            return False
        self._interrupted.add(run_id)
        return True

    def is_running(self, run_id):
        return run_id in self._active

    def active_run_ids(self):
        return set(self._active)


@pytest.fixture()
def trackable_client(tmp_path):
    directory = tmp_path / "vault"
    directory.mkdir()
    index = InMemoryVaultIndex()
    scanner = FileVaultScanner(directory=directory, index=index)
    vault = VaultService(directory=directory, index=index, scanner=scanner)
    runner = TrackableRunner()
    thread_repository = InMemoryThreadRepository()
    thread_service = ThreadService(repository=thread_repository)
    run_service = RunService(
        runners={runner.provider_name: runner},
        default_provider=runner.provider_name,
        resume_handles=InMemoryStore(),
        thread_service=thread_service,
    )
    app = build_app(run_service, vault, thread_service)
    return TestClient(app), runner


def test_cancel_active_run(trackable_client):
    client, runner = trackable_client
    runner._active.add("run-1")

    resp = client.post("/runs/run-1/cancel")
    assert resp.status_code == 200
    assert resp.json() == {"cancelled": True}
    assert "run-1" in runner._interrupted


def test_list_active_runs(trackable_client):
    client, runner = trackable_client
    runner._active.update({"run-a", "run-b"})

    resp = client.get("/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"] == ["run-a", "run-b"]


def test_post_thread_message_returns_summary(client):
    resp = client.post(
        "/threads/k1/messages",
        json={"author": "alice", "content": "hello"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "echo" in body["summary"]


def test_list_threads_returns_metadata(client):
    client.post(
        "/threads/k1/messages",
        json={"author": "alice", "content": "hello"},
    )
    resp = client.get("/threads")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["threads"]) == 1
    thread = body["threads"][0]
    assert thread["resume_key"] == "k1"
    assert thread["entry_count"] >= 1
    assert thread["last_timestamp"] is not None


def test_get_thread_returns_entries(client):
    client.post(
        "/threads/k1/messages",
        json={"author": "alice", "content": "hello"},
    )
    resp = client.get("/threads/k1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["resume_key"] == "k1"
    assert len(body["entries"]) >= 1
    first = body["entries"][0]
    assert first["author"] == "alice"
    assert first["content"] == "hello"
    assert "timestamp" in first
    assert "attachments" in first


def test_get_thread_not_found(client):
    resp = client.get("/threads/missing")
    assert resp.status_code == 404
