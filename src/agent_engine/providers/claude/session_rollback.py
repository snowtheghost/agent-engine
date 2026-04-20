import json
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def _session_jsonl_path(cwd: str, session_id: str) -> Path:
    slug = "-" + cwd.replace("/", "-").lstrip("-")
    return _CLAUDE_PROJECTS_DIR / slug / f"{session_id}.jsonl"


def rollback_session(cwd: str, session_id: str) -> bool:
    jsonl_path = _session_jsonl_path(cwd, session_id)
    if not jsonl_path.exists():
        return False

    try:
        lines = jsonl_path.read_bytes().splitlines(keepends=True)
    except OSError:
        return False

    last_enqueue_index: int | None = None
    for i in range(len(lines) - 1, -1, -1):
        try:
            entry = json.loads(lines[i])
        except (json.JSONDecodeError, ValueError):
            continue
        if entry.get("type") == "queue-operation" and entry.get("operation") == "enqueue":
            last_enqueue_index = i
            break

    if last_enqueue_index is None or last_enqueue_index == 0:
        return False

    truncated = b"".join(lines[:last_enqueue_index])
    try:
        jsonl_path.write_bytes(truncated)
    except OSError:
        return False

    logger.info(
        "session_rolled_back",
        session_id=session_id,
        original_lines=len(lines),
        kept_lines=last_enqueue_index,
        removed_lines=len(lines) - last_enqueue_index,
    )
    return True
