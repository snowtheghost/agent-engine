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
│   └── vault/chunk.py               # VaultChunk, VaultSearchHit
├── application/
│   ├── run/runner/runner.py         # Runner Protocol
│   ├── run/service/run_service.py   # RunService
│   ├── run/service/resume_handle_store.py
│   ├── vault/index/vault_index.py   # VaultIndex ABC
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
│   ├── vault/chunker.py                    # markdown → chunks (by ##/### headings)
│   ├── vault/file_vault_scanner.py         # directory scanner + chunk index sync
│   ├── vault/in_memory_vault_index.py      # token-cosine VaultIndex for tests
│   ├── vault/numpy_vault_index.py          # production VaultIndex adapter over NumpyVectorStore
│   ├── vault/numpy_vector_store.py         # persistent numpy-backed vector store
│   ├── vault/embedding.py                  # nomic-embed-text-v1.5 with asymmetric prefixing
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

The vault is a directory of free-form markdown files. Files are the source of truth — written, edited, deleted on disk by any tool. The engine chunks each file and indexes chunks for semantic search.

### Model

- `VaultChunk(chunk_id, file_path, heading, content, tags)`. `file_path` is relative to the vault root. `chunk_id` is a deterministic `md5(file_path:heading:index:content_prefix)`.
- `VaultSearchHit(chunk, score, path)` where `path` is the absolute filesystem path of the backing file.

### Storage

- Markdown files live anywhere under `config.vault.directory`. The scanner recurses.
- Optional YAML frontmatter (`tags`, `people`, `date`, etc.) between `---` fences. Only `tags` currently flows into chunk metadata; other fields pass through untouched on disk.
- Files are the source of truth. Deleting, editing, moving the file all propagate at the next scan.
- Hidden paths (any component starting with `.`) are ignored.

### Chunker

- `chunker.chunk_markdown(text, file_path)` splits by H2 (`##`) and H3 (`###`) headings. Sections shorter than 20 characters are dropped. Files without headings produce one chunk over the whole body.
- Each chunk carries file tags from frontmatter plus the nearest heading.

### VaultIndex

- `VaultIndex` ABC in `application/vault/index/vault_index.py`. Operations: `upsert(chunks)`, `delete_by_file(file_path)`, `search(query, limit, file_filter=None)`, `file_paths()`, `count()`, `close()`.
- Two implementations:
  - `NumpyVaultIndex` (production) — adapts `NumpyVectorStore` to the chunk interface. Persistence + embeddings.
  - `InMemoryVaultIndex` (tests, dev) — token-cosine over lowercase word tokens. Stateless.

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

### Scanner

- `VaultScanner` ABC in `application/vault/scanner/vault_scanner.py`. `scan(force=False) -> ScanReport(indexed_files, skipped_unchanged, removed_files, total_files, total_chunks)`.
- `FileVaultScanner` walks the vault directory recursively for `.md` files. Per file: checksum (MD5) vs previous; if changed, delete existing chunks for that file, chunk, upsert. Deleted files have their chunks removed. Checksums persisted at `{vault.directory}/.vault_checksums.json`.
- Invoked once at engine startup from `build_engine`. Handles files edited directly on disk.

### Service

- `VaultService.write(title, content, tags=(), subdirectory=None)` → writes a slugified markdown file with frontmatter and an H1, chunks and upserts immediately, returns the written `Path`.
- `VaultService.search(query, limit=5, file_filter=None)` → returns `list[VaultSearchHit]`.
- `VaultService.recall(file_path)` → returns the full markdown body or `None`. Accepts either a vault-relative path or an absolute path under the vault root.
- `VaultService.files()` → `set[str]` of relative paths currently indexed.
- `VaultService.count()` → chunk count.
- `VaultService.rescan(force=False)` → run the scanner.

### Tools

- `tools/vault_tools.py` wraps the service as three MCP tools (`vault_write`, `vault_search`, `vault_recall`) and returns an `McpSdkServerConfig` via `build_vault_mcp_server(vault_service)`.
- `vault_search` output includes the file path, heading, and score for each chunk.

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
- `GET /health` — status + active run count + total chunk count.
- `GET /vault/search?q=...&limit=...&file=...` — top-k chunks, each with file path, heading, score.
- `GET /vault/recall?path=...` — full markdown body of a vault file.
- `POST /vault/entries` — write a new markdown file `{title, content, tags?, subdirectory?}`.
- Served by Uvicorn on `http.host:http.port` (default `127.0.0.1:8938`).

### Discord

- Own bot token. Optional.
- If `channel_id` is set, listens only in that channel and its threads.
- New message in the target channel → creates a thread and dispatches. Message in a thread → dispatches with `resume_key = thread.id`.
- Results sent in ≤`character_limit` chunks. Errors prefixed with `[error]`.

### CLI

- `agent-engine serve` — start all enabled intakes.
- `agent-engine run --prompt "..." [--resume-key KEY] [--model ...]`
- `agent-engine vault search QUERY [--limit N] [--file PATH]` / `agent-engine vault list` / `agent-engine vault recall PATH`
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

1. **Auto-interrupt on dispatch**: `RunService.dispatch()` tracks active runs by `resume_key`. When a new dispatch arrives for a key with an active run, the service interrupts the running session and waits for it to finish (up to 30s timeout) before starting the new one.
2. **Manual cancel**: `POST /runs/{run_id}/cancel` → `RunService.interrupt(run_id)` → `Runner.interrupt(run_id)`.
3. **Claude provider**: `ProcessManager` (`providers/claude/process_manager.py`) tracks active `ClaudeSDKClient` instances by `run_id`. On interrupt, calls `client.interrupt()` on the SDK client, marks the run as interrupted.
4. **Run lifecycle**: Runner registers the client with `ProcessManager` at session start, unregisters at session end. After a session completes, `consume_interrupted(run_id)` checks if the run was interrupted. If so, error results are converted to success with empty output.
5. **Codex provider**: Stub returns `False` (no-op).
6. **HTTP**: `GET /runs` lists active run ids. `GET /health` includes `active_runs`.

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
