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

- **Integrations** receive requests in native protocols (Discord messages, HTTP requests, CLI args). They translate to `RunService.submit_message(resume_key, author, content)` (for durable conversational sources like Discord) or `RunService.dispatch(prompt, resume_key?, model?)` (for one-shot HTTP/CLI callers) and translate `RunResult` back to native output.
- **Core** (application layer) owns run dispatch, resume-handle persistence, durable thread storage, vault write/search/recall.
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
│   ├── thread/model/thread.py       # AttachmentMetadata, ThreadEntry, Thread
│   ├── thread/model/chunk.py        # ThreadChunk, ThreadSearchHit
│   └── vault/chunk.py               # VaultChunk, VaultSearchHit
├── application/
│   ├── run/runner/runner.py         # Runner Protocol
│   ├── run/service/run_service.py   # RunService
│   ├── run/service/resume_handle_store.py
│   ├── indexing/scheduler.py                    # IndexingScheduler Protocol
│   ├── thread/index/thread_index.py             # ThreadIndex ABC
│   ├── thread/repository/thread_repository.py    # ThreadRepository ABC
│   ├── thread/repository/thread_cursor_store.py  # ThreadCursorStore ABC
│   ├── thread/scanner/thread_scanner.py         # ThreadScanner ABC, ThreadScanReport
│   ├── thread/service/thread_service.py          # ThreadService
│   ├── vault/index/vault_index.py   # VaultIndex ABC
│   ├── vault/scanner/vault_scanner.py        # VaultScanner ABC, ScanReport
│   ├── vault/service/vault_service.py
│   └── integration/intake.py        # Intake ABC
├── integrations/
│   ├── discord/bot.py               # DiscordIntake
│   ├── slack/bot.py                 # SlackIntake
│   ├── http/server.py               # HttpIntake + FastAPI app
│   ├── watcher/vault_watcher.py     # VaultWatcher (filesystem → ingest/evict)
│   ├── skills/installer.py          # bundle skills into cwd/.claude/skills/
│   ├── skills/bundled/remember/SKILL.md
│   ├── skills/bundled/recall/SKILL.md
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
│   ├── indexing/async_worker.py               # AsyncIndexingWorker (shared indexing loop)
│   ├── indexing/inline_scheduler.py           # InlineIndexingScheduler (synchronous fallback)
│   ├── thread/chunker.py                      # ThreadEntry → ThreadChunk (one chunk per entry, attachments inlined)
│   ├── thread/in_memory_thread_index.py       # token-cosine ThreadIndex for tests
│   ├── thread/indexing_thread_repository.py   # ThreadRepository decorator that schedules indexing on append/delete
│   ├── thread/jsonl_thread_scanner.py         # startup scan that reindexes thread JSONL files when checksums change
│   ├── thread/numpy_thread_index.py           # production ThreadIndex adapter over NumpyVectorStore
│   ├── thread/persistence/jsonl_thread_repository.py   # append-only JSONL thread store
│   ├── vault/chunker.py                    # markdown → chunks (by ##/### headings)
│   ├── vault/file_vault_scanner.py         # directory scanner + chunk index sync
│   ├── vault/in_memory_vault_index.py      # token-cosine VaultIndex for tests
│   ├── vault/numpy_vault_index.py          # production VaultIndex adapter over NumpyVectorStore
│   ├── vault/numpy_vector_store.py         # persistent numpy-backed vector store
│   ├── vault/embedding.py                  # nomic-embed-text-v1.5 with asymmetric prefixing
│   ├── persistence/database.py             # sqlite schema (resume handles + thread cursors)
│   ├── persistence/sqlite_resume_handle_store.py
│   ├── persistence/sqlite_thread_cursor_store.py       # SQLite ThreadCursorStore
│   ├── system/config/config.py             # YAML config loader
│   └── system/logging/logging.py           # structlog + stdlib logging setup
└── tools/
    ├── response_tools.py            # stay_silent
    ├── thread_tools.py              # thread_recall / thread_list / thread_search
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
- Invoked once at engine startup from `build_engine`. Handles files that changed while the engine was down.

### Watcher

- `integrations/watcher/vault_watcher.py` defines `VaultWatcher(Intake)` — a filesystem watcher using `watchfiles.awatch`.
- Reacts to `.md` / `.markdown` changes under `config.vault.directory`. Hidden paths (any component starting with `.`) are ignored.
- Added or modified files → `VaultService.ingest(path)` (re-chunks + re-upserts).
- Deleted files → `VaultService.evict(path)` (removes chunks for that file).
- Non-markdown writes are dropped.
- Debounce 500ms, step 100ms, recursive.
- Enabled by default; disable per-run with `--no-watcher`. The initial scan still runs at startup; the watcher handles everything after.

### Service

- `VaultService.write(title, content, tags=(), subdirectory=None)` → writes a slugified markdown file with frontmatter and an H1, schedules chunk + upsert via the injected `IndexingScheduler`, returns the written `Path`. File is persisted before the call returns; index updates happen on the scheduler (async worker in production, inline in tests / by default).
- `VaultService.search(query, limit=5, file_filter=None)` → returns `list[VaultSearchHit]`.
- `VaultService.recall(file_path)` → returns the full markdown body or `None`. Accepts either a vault-relative path or an absolute path under the vault root.
- `VaultService.ingest(path)` → schedules chunk + upsert for a specific file by absolute path. Returns chunk count computed synchronously (index update may lag when using an async scheduler). Used by the watcher.
- `VaultService.evict(path)` → schedules chunk removal for a specific file. Returns `1` when the path resolves into the vault (eviction was scheduled) or `0` when the path is outside the vault. Used by the watcher.
- `VaultService.files()` → `set[str]` of relative paths currently indexed.
- `VaultService.count()` → chunk count.
- `VaultService.rescan(force=False)` → run the scanner.

### Tools

- `tools/vault_tools.py` wraps the service as three MCP tools (`vault_write`, `vault_search`, `vault_recall`) and returns an `McpSdkServerConfig` via `build_vault_mcp_server(vault_service)`.
- `vault_search` output includes the file path, heading, and score for each chunk.
- `tools/thread_tools.py` wraps `ThreadService` (and an optional `ThreadIndex`) as three MCP tools (`thread_recall`, `thread_list`, `thread_search`) and returns an `McpSdkServerConfig` via `build_thread_mcp_server(thread_service, index=thread_index)`. Registered alongside the vault server by `main._build_runners`. `thread_search` returns `(score, resume_key#entry_index, author, timestamp, preview)` per hit; when no index is configured it returns a "not available" message.
- `tools/response_tools.py` exposes one MCP tool (`stay_silent(reason)`) via `build_response_mcp_server()`. The agent calls it to decide not to reply this turn; the tool logs the reason via structlog and returns an acknowledgement to the model. Combined with the integration behavior below (skip posting when `RunResult.summary` and `.error` are both empty), this gives the agent an explicit "no-reply" channel.

### Skills

Tools expose raw capability; skills expose policy. The engine bundles skill definitions inside the package and materializes them into `{cwd}/.claude/skills/{name}/SKILL.md` at startup so the Claude SDK discovers them through its existing `project` setting source.

- `integrations/skills/installer.py` defines `install_bundled_skills(cwd)`. Reads `SKILL.md` files from the `agent_engine.integrations.skills.bundled` package resources, writes them into `{cwd}/.claude/skills/{name}/SKILL.md`. Idempotent: unchanged content is left alone, drifted content is overwritten.
- `build_engine(cwd)` calls the installer after the startup vault scan.
- `ClaudeCodeRunner` sets `skills="all"` on `ClaudeAgentOptions` so every discovered skill is loaded into the agent.

Bundled skills:
- `remember` — save factual knowledge. Reads the vault routing map (`Index.md`), dedupes against existing files, updates or writes through `vault_write`.
- `recall` — search the vault semantically before answering. Uses `vault_search` and `vault_recall`, triangulates across multiple queries.

Packaging: `pyproject.toml` includes `tool.setuptools.package-data = { "agent_engine.integrations.skills.bundled" = ["**/SKILL.md"] }` so the markdown ships with the wheel.

## Resume handles

- `ResumeHandle(provider: str, session_id: str)`.
- `ResumeHandleStore` ABC persists `resume_key → ResumeHandle`. SQLite impl keys on `resume_key` in the `resume_handles` table. SQLite is used only for resume handles and thread cursors; vault entries and thread entries live as files.
- Integrations supply a stable `resume_key` per logical conversation (e.g. Discord thread id). `RunService` fetches the matching handle, passes it to the runner, and persists the runner's returned handle.

## Threads

Durable per-conversation history, keyed on `resume_key`. Persistence of entries matches the vault pattern (files on disk, one per thread); the read cursor lives in SQLite for fast upsert. Entries are indexed for semantic search mirroring the vault pipeline.

### Model

- `AttachmentMetadata(path, filename, content_type, size, description)` — frozen. `description` carries optional vision text.
- `ThreadEntry(author, content, attachments, timestamp)`.
- `Thread(resume_key, entries, read_cursor)` with `append(entry)` and `unread_from(cursor) -> list[ThreadEntry]`.
- `ThreadChunk(chunk_id, resume_key, entry_index, author, timestamp, content)`. One chunk per `ThreadEntry`. `chunk_id` is a deterministic `md5(resume_key:entry_index:content_prefix)`. `content` combines the entry body with any attachment descriptions so vision captions are findable by search.
- `ThreadSearchHit(chunk, score)`.
- `AGENT_AUTHOR = "agent"` is the reserved author string for replies written by `ThreadService.log_reply`. Only entries whose author is not `AGENT_AUTHOR` count as pending prompts.

### Persistence layout

- One `{data_dir}/threads/{slug}.jsonl` per thread. Slug is `resume_key` with anything outside `[A-Za-z0-9_-]` replaced by `_`.
- Append-only, one JSON record per line: `{author, content, timestamp, attachments?}`. On load, corrupt lines are skipped with a structlog warning.
- Thread read cursor stored in SQLite table `thread_cursors(resume_key TEXT PRIMARY KEY, cursor INTEGER, updated_at TEXT)` via `SqliteThreadCursorStore`. Cursor advances only on `acknowledge`, never on read.
- `ThreadRepository.append(resume_key, entry) -> int` returns the zero-based index of the just-appended entry. `JsonlThreadRepository` caches the per-key count in memory after the first probe (line count on open) so subsequent appends are O(1). `delete` clears the cached count.

### Service

- `ThreadService.handle_message(resume_key, entry, interrupt=True) -> str | None` — appends and returns the next pending prompt string (or `None` if no pending non-agent entries remain).
- `ThreadService.log_reply(resume_key, content)` — appends a `ThreadEntry(author="agent", ...)` with the current timestamp.
- `ThreadService.acknowledge(resume_key, cursor)` — advances the read cursor.
- `ThreadService.get_pending_prompts(resume_key) -> tuple[str, int] | None` — returns `(combined_prompt, new_cursor)` for all unread non-agent entries. New cursor is `len(entries)` at call time.
- `ThreadService.get_thread(resume_key) -> Thread | None`.
- `ThreadService.list_threads(limit=50, offset=0) -> list[str]` — resume_keys most-recently-updated first.
- Single-entry format: `"[From: <author>]\n\n<content>"` with an optional `[Attachments:]` block.
- Multi-entry format is prefixed with `"[Queued messages while you were working:]\n"` followed by blank-line-separated entry blocks.

### ThreadIndex

- `ThreadIndex` ABC in `application/thread/index/thread_index.py`. Operations: `upsert(chunks)`, `delete_by_resume_key(resume_key)`, `search(query, limit, resume_key_filter=None)`, `resume_keys()`, `count()`, `close()`.
- Two implementations:
  - `NumpyThreadIndex` (production) — adapts `NumpyVectorStore` to the thread chunk interface. Reuses the shared `NumpyVectorStore` impl with `name="thread"`, persisted under `{data_dir}/.store/` alongside the vault store.
  - `InMemoryThreadIndex` (tests) — token-cosine over lowercase word tokens. Stateless.

### IndexingThreadRepository

- Wraps a `ThreadRepository` and a `ThreadIndex` with an `IndexingScheduler`. On `append`: forwards to the inner repository, then chunks the newly appended entry and schedules an index upsert. On `delete`: forwards then schedules a `delete_by_resume_key`. `load`, `list_keys`, `update_cursor` pass through unchanged.
- Registered as the repository in `ThreadService` in production so every append ends up in the index.

### ThreadScanner

- `ThreadScanner` ABC in `application/thread/scanner/thread_scanner.py`. `scan(force=False) -> ThreadScanReport(indexed_threads, skipped_unchanged, removed_threads, total_threads, total_chunks)`.
- `JsonlThreadScanner` walks `{data_dir}/threads/*.jsonl`. Per thread: MD5 checksum vs previous; on mismatch, `delete_by_resume_key` the index then chunk all entries and upsert. Threads whose file is missing have their chunks removed. Checksums persisted at `{data_dir}/threads/.thread_checksums.json`.
- Invoked once at engine startup from `build_engine`, after the vault scan. Handles threads that changed while the engine was down (e.g. writes from a stopped-engine integration).

### Integrations

See below under `## Integrations` and `## Interrupt flow`.

## Indexing

Chunk+embed work for both vault writes and thread appends flows through a shared `IndexingScheduler` so agent-facing code paths don't block on embedding.

### Scheduler

- `IndexingScheduler` Protocol in `application/indexing/scheduler.py`. Single method: `schedule(job: Callable[[], None], *, name: str) -> None`. Fire-and-forget; no return value.
- `InlineIndexingScheduler` (`infrastructure/indexing/inline_scheduler.py`) runs the job immediately in the caller's thread. Used by `VaultService` when no explicit scheduler is injected, which keeps unit tests synchronous.
- `AsyncIndexingWorker` (`infrastructure/indexing/async_worker.py`) runs a single background asyncio task that pulls jobs off an `asyncio.Queue` and executes each in a thread-pool executor (`asyncio.to_thread`). Vault writes and thread appends share one worker and one queue. `start()` spawns the task; `stop()` drains the queue, cancels the task, and is idempotent. `drain()` awaits queue completion (used in tests). Jobs scheduled after `stop()` are dropped with a warning.

### Lifecycle integration

- `build_engine` constructs an `AsyncIndexingWorker`, passes it as the scheduler to `VaultService`, and wraps the base `JsonlThreadRepository` with `IndexingThreadRepository(inner, thread_index, worker)` before handing to `ThreadService`.
- The vault and thread scanners run once during `build_engine` using the indexes directly (not through the scheduler), so engine startup reaches a consistent state before any intake starts accepting traffic.
- `run_engine` awaits `worker.start()` after intakes are built and before they start. On shutdown, intakes stop first, then `worker.stop()` drains pending jobs, then the DB connection closes.

## Config

- Config at `{data-dir}/config.yaml`.
- Default data-dir: `~/.agent-engine/`. Override with `--data-dir`.
- Default vault directory: `{data-dir}`. Override with `vault.directory` in config.
- Precedence: config file > defaults, with env overrides on top.
- Env overrides: `AGENT_ENGINE_DISCORD_TOKEN`, `AGENT_ENGINE_DISCORD_CHANNEL_ID`, `AGENT_ENGINE_SLACK_BOT_TOKEN`, `AGENT_ENGINE_SLACK_APP_TOKEN`, `AGENT_ENGINE_SLACK_CHANNELS` (comma-separated), `AGENT_ENGINE_HTTP_PORT`, `AGENT_ENGINE_LOG_LEVEL`.
- Config object is immutable (`@dataclass(frozen=True)`).
- Database, vault directory, and vector store all live under `data-dir` by default. No files are written to `cwd`.

## Integrations

### HTTP

- `POST /runs` — `{prompt, resume_key?, model?}` → `RunResult` (flattened) or `null` if queued. Routes through `RunService.dispatch`. When a `resume_key` is supplied the request is treated as a durable thread message authored by `"integration"`.
- `POST /runs/{run_id}/cancel` — interrupts a running run.
- `GET /runs` — active run ids.
- `POST /threads/{resume_key}/messages` — `{author, content}` → `RunResult` (flattened) or `null` if the message was queued onto an already-running drainer.
- `GET /threads` — `{threads: [{resume_key, entry_count, last_timestamp}]}`.
- `GET /threads/{resume_key}` — full thread as JSON (`resume_key`, `read_cursor`, `entries: [{author, content, timestamp, attachments}]`).
- `GET /health` — status + active run count + total chunk count.
- `GET /vault/search?q=...&limit=...&file=...` — top-k chunks, each with file path, heading, score.
- `GET /vault/recall?path=...` — full markdown body of a vault file.
- `POST /vault/entries` — write a new markdown file `{title, content, tags?, subdirectory?}`.
- Served by Uvicorn on `http.host:http.port` (default `127.0.0.1:8938`).

### Discord

- Own bot token. Optional.
- If `channel_id` is set, listens only in that channel and its threads.
- New message in the target channel → creates a thread and submits through `RunService.submit_message(resume_key=str(thread.id), author=message.author.display_name, content=prompt)`. Message in a thread → same call with the existing thread id as the `resume_key`.
- If `submit_message` returns a `RunResult`, the summary is sent in ≤`character_limit` chunks. If it returns `None`, the caller sends nothing — the drainer from the active run already owns the reply.
- When the returned `RunResult` has both `summary` and `error` empty, the intake skips posting entirely (silence path for `stay_silent` tool calls).
- Messages sent during an active run are appended to the durable thread and replayed on the next drain as a single combined prompt starting with `"[Queued messages while you were working:]"`.

### Slack

- Own bot and app tokens (xoxb + xapp). Optional. Parallel to Discord; both can run side by side.
- Socket Mode via `slack-bolt`'s `AsyncSocketModeHandler`. No public-facing HTTP endpoint required.
- Listens to `message` events. Ignores bot messages (`bot_id` present), subtype events (e.g. `message_changed`), empty text, and any channel not in `monitored_channels` (exact ID match).
- Resume key: `slack:{channel_id}:{thread_ts or ts}`. Top-level messages use their own `ts`; replies in a thread use the parent's `thread_ts`. The channel prefix prevents cross-channel collisions.
- User name resolved via `users.info` and cached per-instance (display name → real name → user ID fallback).
- Before dispatch: adds a `:eyes:` reaction to the triggering message as a lightweight "working" indicator. Removes it on every exit path (success, error, silence, drainer-queued) via `finally`, so the reaction behaves like a typing indicator — on while the handler is processing, off once it returns. Failures to add or remove are logged at debug and do not block.
- Dispatches through `RunService.submit_message(resume_key=..., author=user_name, content=text)`.
- If `submit_message` returns a `RunResult`, the summary (or error) is posted via `chat.postMessage` in-thread, chunked at `character_limit` (default 40000). If it returns `None`, the active drainer owns the reply — same contract as Discord.
- When the returned `RunResult` has both `summary` and `error` empty, the intake skips posting (silence path).
- Dispatch failures convert to an `[error] ...` reply in the thread.

### CLI

- `agent-engine serve [--no-discord] [--no-http] [--no-slack] [--no-watcher]` — start all enabled intakes.
- `agent-engine run --prompt "..." [--resume-key KEY] [--model ...]`
- `agent-engine vault search QUERY [--limit N] [--file PATH]` / `agent-engine vault list` / `agent-engine vault recall PATH`
- `agent-engine thread list [--limit N]` / `agent-engine thread recall RESUME_KEY`
- `agent-engine --cwd PATH --data-dir PATH` sets the project directory (default: `.`) and data directory (default: `~/.agent-engine/`).

## Providers

### Claude Code (`providers/claude/`)

- `ClaudeCodeRunner` wraps `claude_agent_sdk.ClaudeSDKClient`.
- Builds `ClaudeAgentOptions` with `cwd`, `mcp_servers` (engine-supplied vault tools plus any `.mcp/*.json` in `cwd`), `resume`, `allowed_tools` (all `mcp__<server>` servers), `disallowed_tools=["Task","Agent"]`, `thinking={"type":"adaptive"}`, `effort="max"`, `permission_mode="bypassPermissions"`, `system_prompt={"type":"preset","preset":"claude_code"}`.
- The `claude_code` system-prompt preset keeps the CLI on its default behavior, which auto-loads `CLAUDE.md` from the project `cwd` (plus any parent `CLAUDE.md` chain). Leaving `system_prompt` unset causes the SDK to emit `--system-prompt ""` (explicit empty), which suppresses default behavior and the CLAUDE.md chain.
- Streams assistant messages, logs tool executions via `tool_detail.extract_tool_detail`, collects `ResultMessage` into `RunResult`.
- On resume with a stale session id, attempts one rollback via `session_rollback.rollback_session()` before giving up.
- Token refresh via `token.ensure_token_fresh()` before every run; reads `~/.claude/.credentials.json`.
- Interrupt handling converts error results in interrupted runs to success without output.

### Codex (`providers/codex/`)

- `CodexRunner` stub. `NotImplementedError`. Lands properly when codex CLI / API story is real.

## Interrupt flow

Sessions can be cancelled mid-run via `Runner.interrupt(run_id)`. The flow:

1. **Thread-driven drainer**: `RunService.submit_message(resume_key, author, content)` appends the entry through `ThreadService.handle_message`. If no drainer is currently active for `resume_key`, the service claims the key and loops `get_pending_prompts → _execute → log_reply → acknowledge` until no unread non-agent entries remain. The cursor advances only on `acknowledge`, so an interrupted execute is safe to replay.
2. **Queue-while-active**: If a drainer is already active for `resume_key`, `submit_message` appends the entry and calls `Runner.interrupt(run_id)` on the active run, then returns `None`. The active drainer reads the new pending prompt on its next iteration, which combines any queued entries into a single `"[Queued messages while you were working:]"` prompt.
3. **Auto-interrupt for non-thread dispatch**: Legacy `dispatch(prompt, resume_key=...)` with no thread service configured still tracks active runs by `resume_key` and interrupts a stale run before launching a new one (30s wait).
4. **Manual cancel**: `POST /runs/{run_id}/cancel` → `RunService.interrupt(run_id)` → `Runner.interrupt(run_id)`.
5. **Claude provider**: `ProcessManager` (`providers/claude/process_manager.py`) tracks active `ClaudeSDKClient` instances by `run_id`. On interrupt, calls `client.interrupt()` on the SDK client, marks the run as interrupted.
6. **Run lifecycle**: Runner registers the client with `ProcessManager` at session start, unregisters at session end. After a session completes, `consume_interrupted(run_id)` checks if the run was interrupted. If so, error results are converted to success with empty output.
7. **Codex provider**: Stub returns `False` (no-op).
8. **HTTP**: `GET /runs` lists active run ids. `GET /health` includes `active_runs`.

## Lifecycle

`main.run_engine(cwd, data_dir, disable_discord, disable_http, disable_watcher)`:

1. `build_engine(cwd)` — load config, configure logging, open SQLite, construct an `AsyncIndexingWorker`, build vault service + scanner (scheduler-aware, run one scan to index any out-of-band files), install bundled skills into `{cwd}/.claude/skills/`, build thread service (JSONL repository wrapped in `IndexingThreadRepository` + SQLite cursor store), thread scanner (run one scan), runner (receives vault and thread MCP servers, the thread server also gets the `ThreadIndex` so `thread_search` works), resume store, `RunService`. Vault uses `NumpyVectorStore` persisted to `{data-dir}/.store/` with `nomic-embed-text-v1.5` embeddings; thread chunks use the same store dir under `name="thread"`.
2. `_build_intakes()` — instantiate `VaultWatcher`, HTTP, and Discord intakes per config and flags.
3. Start the indexing worker, then start each intake sequentially. Wait on `stop_event` (SIGINT/SIGTERM).
4. On shutdown: stop intakes in reverse order, stop the indexing worker (drains queue), close SQLite.

## What this engine does not do

- No Airy-specific tooling, no mind/experience/identity concept.
- No SSH, rsync, sync_watcher, or remote execution.
- No world routing.
- No per-run cwd override.
- No automatic code execution outside what the chosen provider already supports.
