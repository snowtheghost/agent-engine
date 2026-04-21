# Agent Engine

Provider-agnostic runtime for AI agents with per-project persistent knowledge.

Point it at a directory. You get an agent that knows your project and remembers across sessions. Talk to it over Discord, HTTP, or the CLI. Swap the provider — Claude Code today, Codex tomorrow — without touching the rest of the stack.

## Architecture

```
Integrations (Discord, HTTP, CLI)  →  Engine Core  →  Providers (Claude Code, Codex, ...)
```

- **Integrations** translate their native protocol into `RunService.submit_message()` (durable conversations) or `RunService.dispatch()` (one-shot prompts).
- **Core** owns runs, resume handles, durable threads, and the vault.
- **Providers** execute one agent turn and return a `RunResult`.

Every session can write to the vault. Every session can search it semantically. The vault lives under `.agent-engine/` in the target directory and travels with the project.

## Quickstart

### Install

```bash
git clone git@github.com:snowtheghost/agent-engine.git
cd agent-engine
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Configure (optional)

Defaults work for most cases. To set a Discord token and channel:

```bash
mkdir -p ~/.agent-engine
cp config.example.yaml ~/.agent-engine/config.yaml
# edit ~/.agent-engine/config.yaml
```

Or set environment variables:

```bash
export AGENT_ENGINE_DISCORD_TOKEN=...
export AGENT_ENGINE_DISCORD_CHANNEL_ID=...
```

### Run

```bash
# Start the engine for the current directory
agent-engine --cwd . serve

# Single-prompt mode (CLI)
agent-engine --cwd . run --prompt "Explain the auth flow"

# Search the vault
agent-engine --cwd . vault search "auth flow"

# List indexed vault file paths
agent-engine --cwd . vault list

# Read a vault file
agent-engine --cwd . vault recall Architecture/auth.md

# HTTP API
curl http://127.0.0.1:8938/health
curl -X POST http://127.0.0.1:8938/runs \
  -H 'content-type: application/json' \
  -d '{"prompt": "Explain the auth flow"}'
curl 'http://127.0.0.1:8938/vault/search?q=auth'
```

### Disable integrations

```bash
agent-engine --cwd . serve --no-discord --no-http
```

### Discord

- Own bot token. Set `AGENT_ENGINE_DISCORD_TOKEN` / `AGENT_ENGINE_DISCORD_CHANNEL_ID`.
- New message in the target channel creates a Discord thread and dispatches. Messages in an existing thread dispatch with `resume_key = thread.id`.
- Messages sent during an active run are appended to the durable thread and replayed as a single combined prompt on the next run (see [Threads](#threads)).

## Vault

The vault is a plain directory of markdown files. Point `vault.directory` at any tree — a `knowledge/vault/` folder, an existing `docs/`, a fresh empty directory — and the engine will chunk it (by `## Section` / `### Subsection`), index each chunk with a semantic embedding, and keep the index synced with disk.

- **Source of truth:** files on disk. Edit, delete, move, or commit them from anywhere. A filesystem watcher keeps the index live; a checksum scan on startup catches anything that changed while the engine was down.
- **Optional frontmatter:** YAML between `---` fences. `tags:` flow into chunk metadata. Other fields (people, date, etc.) pass through untouched.
- **Chunks, not entries:** one file usually produces many chunks, one per section. Each chunk is searchable independently. Files smaller than 20 characters of content under a heading are skipped.
- **Writes are real files:** `vault_write` creates `{slug-of-title}.md` with a title H1 and your content. `subdirectory` routes into a subfolder. Chunk indexing is immediate.

MCP tools exposed to the provider:

- `vault_write(title, content, tags?, subdirectory?)` — create a new markdown file.
- `vault_search(query, limit?, file?)` — semantic search over chunks. Returns file path, heading, preview, score.
- `vault_recall(path)` — full markdown body of a vault file.

Skills bundled with the engine (installed into `{cwd}/.claude/skills/` at startup, discovered via the Claude SDK's project setting source):

- `remember` — wraps `vault_write` with routing, dedup, and update-over-write policy. Reads `Index.md` from the vault to pick the right subdirectory, searches for existing files before writing, and prefers editing over creating duplicates.
- `recall` — wraps `vault_search` + `vault_recall` with "search before you answer" policy. Triangulates across paraphrased queries, opens the file for full context on strong hits, refuses to assert absence without searching.

Write your own skills at `{cwd}/.claude/skills/{name}/SKILL.md`. Bundled skills are refreshed on every engine startup if their content changes.

Index storage (embeddings + metadata) lives at `{data_dir}/.store/`. Checksums at `{vault.directory}/.vault_checksums.json`. Commit the markdown; gitignore the store.

## Threads

Every durable conversation is a `Thread` keyed on `resume_key`. The append-only entry log *is* the inbound message queue — `thread.entries[read_cursor:]` filtered by non-agent authors is exactly the pending work to drain, and it survives restart and is recallable.

- **Storage:** one `{data_dir}/threads/{slug}.jsonl` per thread. One JSON record per line. Corrupt lines are skipped with a warning on load.
- **Cursor:** advanced only by `ThreadService.acknowledge` after a run logs its reply, so an interrupted run is safe to replay. Persisted in the SQLite `thread_cursors` table next to resume handles.
- **Agent author:** replies logged by `ThreadService.log_reply` carry `author="agent"` and are filtered from the next pending batch so the agent never re-reads its own voice.
- **Combined prompt:** if more than one unread non-agent entry is pending, the drainer sends them as one prompt starting with `"[Queued messages while you were working:]"` and a blank-line-separated block per entry. Single-entry prompts are a plain `[From: <author>]\n\n<content>` block.

HTTP:

```
POST /threads/{resume_key}/messages   # {author, content} → RunResult or null if queued
GET  /threads                         # {threads: [{resume_key, entry_count, last_timestamp}]}
GET  /threads/{resume_key}            # full thread with entries and attachments
```

CLI:

```
agent-engine thread list [--limit N]
agent-engine thread recall RESUME_KEY
```

MCP tools exposed to the provider:

- `thread_recall(resume_key)` — full transcript.
- `thread_list(limit?)` — resume_keys, most-recently-updated first.

## Adding a provider

Implement the `Runner` protocol at `application/run/runner/runner.py`. Register it in `main._build_runner`. That's the entire surface.

## Adding an integration

Implement the `Intake` ABC at `application/integration/intake.py`. Have it translate its native protocol into `RunService.dispatch()` calls. Register it in `main._build_intakes`.

## License

MIT.
