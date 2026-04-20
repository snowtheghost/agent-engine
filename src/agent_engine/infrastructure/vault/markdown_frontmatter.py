import re
from datetime import datetime, timezone
from typing import Any

import yaml

from agent_engine.core.vault.model.entry import VaultEntry


_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def format_entry(entry: VaultEntry) -> str:
    payload: dict[str, Any] = {
        "id": entry.entry_id,
        "kind": entry.kind,
        "title": entry.title,
        "tags": list(entry.tags),
        "created_at": entry.created_at.isoformat(),
    }
    frontmatter = yaml.safe_dump(
        payload,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    body = entry.body.rstrip() + "\n"
    return f"---\n{frontmatter}\n---\n\n{body}"


def parse_entry(text: str) -> VaultEntry | None:
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        return None
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(metadata, dict):
        return None
    entry_id = metadata.get("id")
    kind = metadata.get("kind")
    title = metadata.get("title")
    if not isinstance(entry_id, str) or not isinstance(kind, str) or not isinstance(title, str):
        return None
    tags_raw = metadata.get("tags", [])
    if isinstance(tags_raw, list):
        tags = tuple(str(tag) for tag in tags_raw)
    elif isinstance(tags_raw, str):
        tags = tuple(t.strip() for t in tags_raw.split(",") if t.strip())
    else:
        tags = ()
    created_at = _parse_datetime(metadata.get("created_at"))
    body = match.group(2).rstrip()
    return VaultEntry(
        entry_id=entry_id,
        kind=kind,
        title=title,
        body=body,
        tags=tags,
        created_at=created_at,
    )


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return datetime.now(timezone.utc)
