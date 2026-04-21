# Agent Engine — Specification

Rebuild contract. If the code and this document disagree, this document is wrong; update it.

## Purpose

Agent Engine is a provider-agnostic, integration-agnostic runtime for AI agents. It runs on one machine, against one project directory, and exposes that agent to the outside world through any number of integrations (Discord, HTTP, CLI, future: Slack/web/etc). Every agent run can read from and write to a per-project knowledge vault.

## Non-purposes

- No multi-project routing. One process, one `cwd`, one `data-dir`.
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
│   ├── vault/scanner/vault_scanner.py        # VaultScanner ABC, ScanReport
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
│   ├── vault/file_vault_repository.py      # markdown file repository
│   ├── vault/file_vault_scanner.py         # directory scanner + index sync
│   ├── vault/markdown_frontmatter.py       # YAML frontmatter format/parse
│   ├── vault/in_memory_vector_index.py     # dev/test default
│   ├── vault/numpy_vector_store.py         # persistent numpy-backed vector store
│   ├── vault/persistent_vector_index.py    # VectorIndex adapter over NumpyVectorStore
│   ├── vault/embedding.py                  # nomic-embed-text-v1.5 with asymmetric prefixing
│   ├── vault/sentence_transformers_index.py # legacy (unused in production)
│   ├── persistence/database.py             # sqlite schema (resume handles only)
│   ├── persistence/sqlite_resume_handle_store.py
│   └── system/config/config.py             # YAML config loader
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

### Model

- **Entry shape**: `entry_id` (uuid), `kind` (free-form), `title`, `body`, `tags: tuple[str, ...]`, `created_at` (UTC).
- **Search hit**: `VaultSearchHit(entry, score, path)`. The `path` is the absolute filesystem path of the backing markdown file.

### Storage: markdown files

- Each entry is a `.md` file in `config.vault.directory` named `{entry_id}.md`.
- Frontmatter is YAML between `---` fences with keys `id`, `kind`, `title`, `tags`, `created_at`. The body follows.
- Markdown files are the source of truth. Deleting a file removes the entry. Editing a file changes the entry on the next scan.
- `FileVaultRepository` (`infrastructure/vault/file_vault_repository.py`) implements `VaultRepository` against a directory. Writes are atomic via `tempfile + os.replace`.
- `markdown_frontmatter.format_entry / parse_entry` (`infrastructure/vault/markdown_frontmatter.py`) render and parse the file format.
- `FileVaultScanner` (`infrastructure/vault/file_vault_scanner.py`) walks the vault directory recursively for `.md` files, indexes entries whose file checksum has changed, and removes index entries whose files have disappeared. Checksums are stored at `{vault.directory}/.vault_checksums.json`.

### Vector index

- `VectorIndex` ABC in `application/vault/index/vector_index.py`. Exposes `upsert`, `remove`, `search`, `ids`, `close`.
- Three implementations:
  - `PersistentVectorIndex` (default, production) — adapts `NumpyVectorStore` to the `VectorIndex` interface. Delegates to the store for persistence and semantic search.
  - `InMemoryVectorIndex` (tests and --no-embeddings use) — token-cosine over lowercase word tokens.
  - `SentenceTransformersIndex` (legacy) — pickle-based. Retained for backward compatibility but not used in production.

### NumpyVectorStore

- `NumpyVectorStore` in `infrastructure/vault/numpy_vector_store.py`. Persistent embedding index backed by numpy arrays.
- Stores embeddings as `{store_dir}/{name}_embeddings.npy`, metadata as `{name}_index.json`.
- Operations: batch `upsert(ids, documents, metadatas)`, batch `delete(ids)`, `get(ids?, where?)`, `query(query_texts, n_results, where)`, `reset()`.
- Thread-safe via `Lock`. Loads from disk on init, saves after every mutation.
- Supports metadata filtering with `$and`, `$or`, `$contains`, `$ne`.
- Query uses cosine similarity (dot product on L2-normalized embeddings).

### Embedding

- `embedding.py` in `infrastructure/vault/embedding.py`. Uses `sentence_transformers` with `nomic-ai/nomic-embed-text-v1.5` (768-dim).
- Runs on CPU. Lazy-loads the model on first use.
- Asymmetric prefixing: `search_document:` for indexing, `search_query:` for queries.
- `embed_documents(texts)` and `embed_queries(texts)` are the public functions.

### Store location

- The persistent store lives at `{config.data_dir}/.store/`. Follows the `--data-dir` pattern from the config.
- `PersistentVectorIndex` wraps `NumpyVectorStore` and adapts it to the `VectorIndex` ABC used by the scanner and service.

### Scanner

- `VaultScanner` ABC in `application/vault/scanner/vault_scanner.py`. `scan(force=False) -> ScanReport`.
- `ScanReport(indexed, skipped_unchanged, removed, total)` summarises one pass.
- `FileVaultScanner` is invoked once at engine startup from `build_engine`. It performs delta indexing via file checksums.
- Writes through the service are indexed immediately. The scanner is the authority for drift between files and index (files edited directly on disk, files deleted, files added out of band).

### Service

- `VaultService.write(kind, title, body, tags=())` → writes markdown file via repository, upserts vector entry, returns `VaultEntry`.
- `VaultService.search(query, limit=5)` → asks index for top-k ids, hydrates entries via repository, returns `list[VaultSearchHit]` with paths.
- `VaultService.recall(entry_id)` → reads the markdown file.
- `VaultService.list(limit=100)` → returns recent entries by `created_at`.
- `VaultService.delete(entry_id)` → unlinks the file and removes the index entry.
- `VaultService.count()` → number of vault files.

### Tools

- `tools/vault_tools.py` wraps the service as three MCP tools (`vault_write`, `vault_search`, `vault_recall`) and returns an `McpSdkServerConfig` via `build_vault_mcp_server(vault_service)`.
- `vault_search` output includes the backing file path for each hit.

## Resume handles

- `ResumeHandle(provider: str, session_id: str)`.
- `ResumeHandleStore` ABC persists `resume_key → ResumeHandle`. SQLite impl keys on `resume_key` in the `resume_handles` table. SQLite is used only for resume handles; vault entries live as files.
- Integrations supply a stable `resume_key` per logical conversation (e.g. Discord thread id). `RunService` fetches the matching handle, passes it to the runner, and persists the runner's returned handle.

## Config

- Config at `{data-dir}/config.yaml`.
- Default data-dir: `~/.agent-engine/`. Override with `--data-dir`.
- Default vault directory: `{data-dir}`. Override with `vault.directory` in config.
- Precedence: config file > defaults, with env overrides on top.
- Env overrides: `AGENT_ENGINE_DISCORD_TOKEN`, `AGENT_ENGINE_DISCORD_CHANNEL_ID`, `AGENT_ENGINE_HTTP_PORT`, `AGENT_ENGINE_LOG_LEVEL`.
- Config object is immutable (`@dataclass(frozen=True)`).
- Database, vault directory, and vector store all live under `data-dir` by default. No files are written to `cwd`.

## Integrations

### HTTP

- `POST /runs` — `{prompt, resume_key?, model?}` → `RunResult` (flattened). Dispatches through `RunService`.
- `POST /runs/{run_id}/cancel` — interrupts a running run.
- `GET /runs` — active run ids.
- `GET /health` — status + active run count + vault entry count.
- `GET /vault/search?q=...&limit=...` — top-k hits, each with its backing file `path`.
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
- `agent-engine --cwd PATH --data-dir PATH` sets the project directory (default: `.`) and data directory (default: `~/.agent-engine/`).

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

## Interrupt flow

Sessions can be cancelled mid-run via `Runner.interrupt(run_id)`. The flow:

1. **Request**: `POST /runs/{run_id}/cancel` → `RunService.interrupt(run_id)` → `Runner.interrupt(run_id)`.
2. **Claude provider**: `ProcessManager` (`providers/claude/process_manager.py`) tracks active `ClaudeSDKClient` instances by `run_id`. On interrupt, calls `client.interrupt()` on the SDK client, marks the run as interrupted.
3. **Run lifecycle**: Runner registers the client with `ProcessManager` at session start, unregisters at session end. After a session completes, `consume_interrupted(run_id)` checks if the run was interrupted. If so, error results are converted to success with empty output.
4. **Codex provider**: Stub returns `False` (no-op).
5. **HTTP**: `GET /runs` lists active run ids. `GET /health` includes `active_runs`.

## Lifecycle

`main.run_engine(cwd, data_dir, disable_discord, disable_http)`:

1. `build_engine(cwd)` — load config, configure logging, open SQLite, build vault service + scanner (run one scan to index any out-of-band files), runner, resume store, `RunService`. Vault uses `NumpyVectorStore` persisted to `{data-dir}/.store/` with `nomic-embed-text-v1.5` embeddings.
2. `_build_intakes()` — instantiate HTTP and Discord intakes per config.
3. Start each intake sequentially. Wait on `stop_event` (SIGINT/SIGTERM).
4. On shutdown: stop intakes in reverse order, close SQLite.

## What this engine does not do

- No Airy-specific tooling, no mind/experience/identity concept.
- No SSH, rsync, sync_watcher, or remote execution.
- No world routing.
- No per-run cwd override.
- No automatic code execution outside what the chosen provider already supports.
