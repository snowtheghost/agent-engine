import pytest
from fastapi.testclient import TestClient

from agent_engine.application.run.service.resume_handle_store import ResumeHandleStore
from agent_engine.application.run.service.run_service import RunService
from agent_engine.application.vault.service.vault_service import VaultService
from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run_result import RunResult
from agent_engine.infrastructure.vault.file_vault_repository import FileVaultRepository
from agent_engine.infrastructure.vault.in_memory_vector_index import InMemoryVectorIndex
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
    vault = VaultService(
        repository=FileVaultRepository(tmp_path / "vault"),
        index=InMemoryVectorIndex(),
    )
    run_service = RunService(runner=StubRunner(), resume_handles=InMemoryStore())
    app = build_app(run_service, vault)
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["active_runs"] == []
    assert body["vault_entries"] == 0


def test_post_runs_returns_summary(client):
    resp = client.post("/runs", json={"prompt": "hello", "resume_key": "k1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["summary"] == "echo: hello"
    assert body["resume_provider"] == "stub"
    assert body["resume_session_id"] == "sess-1"


def test_vault_roundtrip(client):
    create = client.post(
        "/vault/entries",
        json={"kind": "note", "title": "OAuth", "body": "PKCE flow", "tags": ["auth"]},
    )
    assert create.status_code == 200
    entry_id = create.json()["entry_id"]

    recall = client.get(f"/vault/entries/{entry_id}")
    assert recall.status_code == 200
    assert recall.json()["title"] == "OAuth"

    search = client.get("/vault/search", params={"q": "PKCE"})
    assert search.status_code == 200
    body = search.json()
    assert body["results"]
    assert body["results"][0]["entry_id"] == entry_id
    assert body["results"][0]["path"].endswith(f"{entry_id}.md")


def test_vault_recall_not_found(client):
    resp = client.get("/vault/entries/missing")
    assert resp.status_code == 404
