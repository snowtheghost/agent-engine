# Agent Engine — Specification

Rebuild contract. If the code and this document disagree, this document is wrong; update it.

## Purpose

Agent Engine is a provider-agnostic, integration-agnostic runtime for AI agents. It runs on one machine, against one project directory, and exposes that agent to the outside world through any number of integrations (Discord, HTTP, CLI, future: Slack/web/etc). Every agent run can read from and write to a per-project knowledge vault.

## Non-purposes

- No multi-project routing. One process, one `cwd`.
- No persona, identity, mind, experience, world concept.
- No remote execution. The engine runs where the code lives.
- No cross-instance state. Two projects means two processes.

## Top-level shape

```
Integrations → Core → Providers
```

- **Integrations** receive requests in native protocols (Discord messages, HTTP requests, CLI args). They translate to `RunService.dispatch(prompt, resume_key, model)` and translate `RunResult` back to native output.
- **Core** (application layer) owns run dispatch, resume-handle persistence, vault write/search/recall.
- **Providers** (infrastructure: `providers/<name>/`) implement `Runner`. They execute an agent turn and return a `RunResult`.

Integrations never import providers. Providers never import integrations. Core mediates both through Protocols/ABCs.

## Layering

Dependencies flow inward. `core → nothing`, `application → core`, `infrastructure|integrations|providers|tools → application|core`, `main → everything`.

```
src/agent_engine/
├── main.py                          # composition root, intake lifecycle
├── core/
│   ├── run/model/run.py             # Run
│   ├── run/model/run_result.py      # RunResult
│   ├── run/model/resume_handle.py   # ResumeHandle
│   └── vault/model/entry.py         # VaultEntry, VaultSearchHit
├── application/
│   ├── run/runner/runner.py         # Runner Protocol
│   ├── run/service/run_service.py   # RunService
│   ├── run/service/resume_handle_store.py
│   ├── vault/repository/vault_repository.py  # VaultRepository ABC
│   ├── vault/index/vector_index.py  # VectorIndex ABC
│   ├── vault/service/vault_service.py
│   └── integration/intake.py        # Intake ABC
├── integrations/
│   ├── discord/bot.py               # DiscordIntake
│   ├── http/server.py               # HttpIntake + FastAPI app
│   └── cli/main.py                  # CLI entrypoint
├── providers/
│   ├── claude/
│   │   ├── runner.py                # ClaudeCodeRunner
│   │   ├── sdk_process.py
│   │   ├── process_manager.py
│   │   ├── retry_policy.py
│   │   ├── token.py
│   │   ├── tool_detail.py
│   │   ├── mcp_discovery.py
│   │   ├── session_state_tracker.py
│   │   └── session_rollback.py
│   └── codex/runner.py              # stub
├── infrastructure/
│   ├── vault/sqlite_vault_repository.py
│   ├── vault/in_memory_vector_index.py       # dev/test default
│   ├── vault/sentence_transformers_index.py  # production default
│   ├── persistence/database.py               # sqlite schema
│   ├── persistence/sqlite_resume_handle_store.py
│   └── system/config/config.py               # YAML config loader
└── tools/
    └── vault_tools.py               # vault_write / vault_search / vault_recall
```

## Runner contract (`application/run/runner/runner.py`)

```python
class Runner(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def run(
        self, prompt: str, *,
        run_id: str,
        resume_handle: ResumeHandle | None,
        model: str | None,
    ) -> RunResult: ...

    async def interrupt(self, run_id: str) -> bool: ...
    def is_running(self, run_id: str) -> bool: ...
    def active_run_ids(self) -> set[str]: ...
```

Runners receive `cwd` at construction, not per-run. Runners never see integrations.

## Intake contract (`application/integration/intake.py`)

```python
class Intake(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
```

Intakes call into `RunService` and `VaultService`. They do not touch providers directly.

## Vault

- **Entry shape**: `entry_id` (uuid), `kind` (free-form), `title`, `body`, `tags: tuple[str, ...]`, `created_at` (UTC).
- **Repository**: `VaultRepository` ABC with SQLite impl in `infrastructure/vault/sqlite_vault_repository.py`. Schema lives in `infrastructure/persistence/database.py`.
- **Vector index**: `VectorIndex` ABC. Two impls:
  - `SentenceTransformersIndex` (default, production) — loads a sentence-transformers model lazily, persists embeddings to `{cwd}/.agent-engine/index.pkl`.
  - `InMemoryVectorIndex` (tests and --no-embeddings use) — token-cosine over lowercase word tokens.
- **Service**: `VaultService.write(kind, title, body, tags=())`, `.search(query, limit=5)`, `.recall(entry_id)`, `.list(limit=100)`, `.delete(entry_id)`, `.count()`.
- **Tools**: `tools/vault_tools.py` wraps the service as three MCP tools (`vault_write`, `vault_search`, `vault_recall`) and returns an `McpSdkServerConfig` via `build_vault_mcp_server(vault_service)`.

## Resume handles

- `ResumeHandle(provider: str, session_id: str)`.
- `ResumeHandleStore` ABC persists `resume_key → ResumeHandle`. SQLite impl keys on `resume_key` in the `resume_handles` table.
- Integrations supply a stable `resume_key` per logical conversation (e.g. Discord thread id). `RunService` fetches the matching handle, passes it to the runner, and persists the runner's returned handle.

## Config

- Global at `~/.agent-engine/config.yaml`.
- Project at `{cwd}/.agent-engine/config.yaml`.
- Precedence: project > global > defaults.
- Env overrides: `AGENT_ENGINE_DISCORD_TOKEN`, `AGENT_ENGINE_DISCORD_CHANNEL_ID`, `AGENT_ENGINE_HTTP_PORT`, `AGENT_ENGINE_LOG_LEVEL`.
- Config object is immutable (`@dataclass(frozen=True)`).

## Integrations

### HTTP

- `POST /runs` — `{prompt, resume_key?, model?}` → `RunResult` (flattened). Dispatches through `RunService`.
- `POST /runs/{run_id}/cancel` — interrupts a running run.
- `GET /runs` — active run ids.
- `GET /health` — status + active run count + vault entry count.
- `GET /vault/search?q=...&limit=...` — top-k hits.
- `GET /vault/entries/{id}` — full entry.
- `POST /vault/entries` — create an entry directly.
- Served by Uvicorn on `http.host:http.port` (default `127.0.0.1:8938`).

### Discord

- Own bot token. Optional.
- If `channel_id` is set, listens only in that channel and its threads.
- New message in the target channel → creates a thread and dispatches. Message in a thread → dispatches with `resume_key = thread.id`.
- Results sent in ≤`character_limit` chunks. Errors prefixed with `[error]`.

### CLI

- `agent-engine serve` — start all enabled intakes.
- `agent-engine run --prompt "..." [--resume-key KEY] [--model ...]`
- `agent-engine vault search|list|recall`
- `agent-engine --cwd PATH` sets the project directory (default: `.`).

## Providers

### Claude Code (`providers/claude/`)

- `ClaudeCodeRunner` wraps `claude_agent_sdk.ClaudeSDKClient`.
- Builds `ClaudeAgentOptions` with `cwd`, `mcp_servers` (engine-supplied vault tools plus any `.mcp/*.json` in `cwd`), `resume`, `allowed_tools` (all `mcp__<server>` servers), `disallowed_tools=["Task","Agent"]`, `thinking={"type":"adaptive"}`, `effort="max"`, `permission_mode="bypassPermissions"`.
- Streams assistant messages, logs tool executions via `tool_detail.extract_tool_detail`, collects `ResultMessage` into `RunResult`.
- On resume with a stale session id, attempts one rollback via `session_rollback.rollback_session()` before giving up.
- Token refresh via `token.ensure_token_fresh()` before every run; reads `~/.claude/.credentials.json`.
- Interrupt handling converts error results in interrupted runs to success without output.

### Codex (`providers/codex/`)

- `CodexRunner` stub. `NotImplementedError`. Lands properly when codex CLI / API story is real.

## Lifecycle

`main.run_engine(cwd, disable_discord, disable_http)`:

1. `build_engine(cwd)` — load config, configure logging, open SQLite, build vault + runner + resume store + `RunService`.
2. `_build_intakes()` — instantiate HTTP and Discord intakes per config.
3. Start each intake sequentially. Wait on `stop_event` (SIGINT/SIGTERM).
4. On shutdown: stop intakes in reverse order, close SQLite.

## What this engine does not do

- No Airy-specific tooling, no mind/experience/identity concept.
- No SSH, rsync, sync_watcher, or remote execution.
- No world routing.
- No per-run cwd override.
- No automatic code execution outside what the chosen provider already supports.
