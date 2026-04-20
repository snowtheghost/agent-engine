from collections.abc import Callable
from typing import Any

_Input = dict[str, Any]
_Extractor = Callable[[_Input], str]


def _file_search(tool_input: _Input) -> str:
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    pattern = tool_input.get("pattern", "")
    if path and pattern:
        return f"{pattern} in {path}"
    return path or pattern


def _bash(tool_input: _Input) -> str:
    return tool_input.get("description") or (tool_input.get("command") or "")[:80]


def _todo_write(tool_input: _Input) -> str:
    todos = tool_input.get("todos", [])
    in_progress = [t for t in todos if t.get("status") == "in_progress"]
    if in_progress:
        return in_progress[0].get("activeForm", f"{len(todos)} items")
    return f"{len(todos)} items"


def _field(key: str, prefix: str = "") -> _Extractor:
    def _extract(tool_input: _Input) -> str:
        value = tool_input.get(key, "")
        return f"{prefix}{value}" if prefix else value

    return _extract


def _empty(tool_input: _Input) -> str:
    return ""


_EXTRACTORS: dict[str, _Extractor] = {
    "Read": _file_search,
    "Glob": _file_search,
    "Grep": _file_search,
    "Bash": _bash,
    "Edit": _field("file_path"),
    "Write": _field("file_path"),
    "WebFetch": _field("url"),
    "WebSearch": _field("query"),
    "Task": _field("description"),
    "TodoWrite": _todo_write,
    "vault_write": _field("title"),
    "vault_search": _field("query"),
    "vault_recall": _field("entry_id"),
}


def _fallback(tool_input: _Input) -> str:
    for value in tool_input.values():
        if isinstance(value, str) and value:
            return value[:80]
    return ""


def extract_tool_detail(tool_name: str, tool_input: dict[str, Any] | None) -> str:
    tool_input = tool_input or {}
    name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
    extractor = _EXTRACTORS.get(name, _fallback)
    return extractor(tool_input)[:120]
