# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dev setup (Python 3.13+):

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Tests, lint, run:

```bash
pytest                              # full suite; uses InMemoryVaultIndex, no model downloads
pytest tests/application/run/       # single directory
pytest tests/vault/test_scanner.py::test_name   # single test
ruff check .                        # required before PR
ruff format .                       # formatter

agent-engine --cwd . serve          # all intakes (Discord, HTTP, watcher)
agent-engine --cwd . serve --no-discord --no-http --no-watcher
agent-engine --cwd . run --prompt "..."     # one-shot
```

`scripts/launch.sh` wraps `agent-engine` for the installed launchd service. `scripts/update.sh` pulls, reinstalls, and reboots the LaunchAgent.

## Source of truth

`SPECIFICATION.md` is the rebuild contract. Any structural change must update it in the same PR; if spec and code disagree, the spec is wrong and needs updating. Read it before making architectural changes.

## Layering

Strict inward dependency flow. Violations break the provider/integration abstraction.

```
core → nothing
application → core
infrastructure | integrations | providers | tools → application | core
main → everything
```

- `core/` is pure domain models (frozen dataclasses). No I/O, no logging.
- `application/` defines `Protocol` / `ABC` contracts and services that orchestrate them.
- `infrastructure/`, `providers/`, `integrations/` are adapters. They depend inward only.
- `integrations/` never import `providers/` and vice versa. `core` mediates via `Runner` (Protocol) and `Intake` (ABC).
- `main.py` is the composition root — the only place that wires concrete implementations together.

## Three subsystems to understand

**Runs + resume handles.** `RunService.dispatch` / `submit_message` in `application/run/service/run_service.py` is the entry point for every request. `Runner` (`application/run/runner/runner.py`) is the provider contract; `ClaudeCodeRunner` is the only real implementation. Resume handles (`ResumeHandle(provider, session_id)`) are persisted per `resume_key` in SQLite so conversations can continue across restarts. When a session id is stale, the Claude runner attempts one `session_rollback` before giving up.

**Threads + drainer.** Durable per-conversation history lives as append-only JSONL files at `{data_dir}/threads/{slug}.jsonl`; read cursor lives in SQLite (`thread_cursors`). The invariant: **the cursor advances only on `acknowledge`, never on read**, so an interrupted run is safe to replay. `submit_message` either starts a drainer for the `resume_key` or, if one is already active, appends the new entry and interrupts the in-flight run — the drainer then picks up all queued entries on its next iteration and combines them into a single `[Queued messages while you were working:]` prompt. Agent replies are logged with `author="agent"` and filtered out of pending prompts.

**Vault.** Markdown files on disk are the source of truth. The chunker splits by `##`/`###` headings (sections under 20 chars dropped). `VaultScanner` runs once at startup (checksum-based, catches offline edits); `VaultWatcher` (watchfiles intake) handles live changes after. The index is `NumpyVaultIndex` over `NumpyVectorStore` with `nomic-ai/nomic-embed-text-v1.5` embeddings (asymmetric prefixing: `search_document:` for upsert, `search_query:` for queries). Tests use `InMemoryVaultIndex` (token-cosine). Store persists at `{data_dir}/.store/`; checksums at `{vault.directory}/.vault_checksums.json`.

## Tools vs skills

MCP tools in `tools/` (`vault_write`, `vault_search`, `vault_recall`, `thread_recall`, `thread_list`) expose raw capability. Skills in `integrations/skills/bundled/{name}/SKILL.md` add policy (dedup, routing, "search before answering"). At startup, `install_bundled_skills(cwd)` copies them into `{cwd}/.claude/skills/` so the Claude SDK discovers them via its `project` setting source. `ClaudeCodeRunner` sets `skills="all"`. Bundled skills ship via `tool.setuptools.package-data` in `pyproject.toml` — remember to keep that glob current if you add new bundled skill assets.

## Data directory conventions

Nothing writes into `cwd` except `{cwd}/.claude/skills/` (skill materialization). Everything else — SQLite DB, vector store, thread JSONL, vault (by default), config — lives under `data_dir` (default `~/.agent-engine/`). Config is `{data_dir}/config.yaml` and is an immutable `@dataclass(frozen=True)`; env vars (`AGENT_ENGINE_*`) override config values.

## Adding a provider or integration

- **Provider:** implement `Runner` in `providers/<name>/runner.py`, register in `main._build_runner`. Constructor takes `cwd`; runners never see integrations.
- **Integration:** implement `Intake` in `integrations/<name>/`, register in `main._build_intakes`. Integrations call `RunService.submit_message` (durable) or `RunService.dispatch` (one-shot) — never the runner directly.

## Testing notes

- `pytest.ini_options` sets `asyncio_mode = "auto"` and `pythonpath = ["src"]`.
- Tests mirror the source tree under `tests/`.
- The real embedding model is never loaded in tests — `InMemoryVaultIndex` stands in. If you add a feature that depends on real embeddings, gate the test appropriately rather than forcing the model download in CI.
