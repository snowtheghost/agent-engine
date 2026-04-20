#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_DIR="${AGENT_ENGINE_CWD:-${HOME}/.agent-engine}"
mkdir -p "${PROJECT_DIR}/.agent-engine"

if ! command -v pass >/dev/null 2>&1; then
    echo "pass CLI not found; install pass or set AGENT_ENGINE_DISCORD_TOKEN manually" >&2
    exit 1
fi

export AGENT_ENGINE_DISCORD_TOKEN="$(pass show agent-engine/discord-bot-token)"

exec "${ENGINE_DIR}/.venv/bin/agent-engine" --cwd "${PROJECT_DIR}" "$@"
