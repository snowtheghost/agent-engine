# Agent Engine

Provider-agnostic runtime for AI agents with per-project persistent knowledge.

Point it at a directory. You get an agent that knows your project and remembers across sessions. Talk to it over Discord, HTTP, or the CLI. Swap the provider — Claude Code today, Codex tomorrow — without touching the rest of the stack.

## Architecture

```
Integrations (Discord, HTTP, CLI)  →  Engine Core  →  Providers (Claude Code, Codex, ...)
```

- **Integrations** translate their native protocol into `RunService.dispatch()`.
- **Core** owns runs, resume handles, and the vault.
- **Providers** execute one agent turn and return a `RunResult`.

Every session can write to the vault. Every session can search it semantically. The vault lives under `.agent-engine/` in the target directory and travels with the project.

## Quickstart

### Install

```bash
git clone https://github.com/<your-org>/agent-engine.git
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

# List recent vault entries
agent-engine --cwd . vault list

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

## Vault

`VaultEntry`: `id`, `kind` (free-form category: decision / pattern / gotcha / api-note / whatever), `title`, `body`, `tags`, `created_at`.

The agent writes entries through an MCP tool `vault_write`. It searches through `vault_search`, recalls by id through `vault_recall`. These are exposed to Claude Code as the `mcp__vault__*` tools. Any future provider wraps them the same way.

Storage: SQLite at `.agent-engine/agent-engine.db` + sentence-transformers index at `.agent-engine/index.pkl`. Commit them if you want shared team memory, gitignore them if private.

## Adding a provider

Implement the `Runner` protocol at `application/run/runner/runner.py`. Register it in `main._build_runner`. That's the entire surface.

## Adding an integration

Implement the `Intake` ABC at `application/integration/intake.py`. Have it translate its native protocol into `RunService.dispatch()` calls. Register it in `main._build_intakes`.

## License

MIT.
