import hashlib
import re

import yaml

from agent_engine.core.vault.chunk import VaultChunk

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_MIN_CONTENT_LENGTH = 20


def chunk_markdown(text: str, file_path: str) -> list[VaultChunk]:
    frontmatter, body = _split_frontmatter(text)
    tags = _extract_tags(frontmatter)

    chunks: list[VaultChunk] = []
    current_section = ""
    current_subsection = ""
    current_content: list[str] = []
    chunk_index = 0

    def flush() -> None:
        nonlocal chunk_index
        content = "\n".join(current_content).strip()
        if len(content) < _MIN_CONTENT_LENGTH:
            return
        heading = current_subsection or current_section or "General"
        chunk_id = _chunk_id(file_path, heading, chunk_index, content)
        chunk_index += 1
        chunks.append(
            VaultChunk(
                chunk_id=chunk_id,
                file_path=file_path,
                heading=heading,
                content=content,
                tags=tags,
            )
        )

    for line in body.split("\n"):
        if line.startswith("## "):
            flush()
            current_section = line.lstrip("# ").strip()
            current_subsection = ""
            current_content = []
        elif line.startswith("### "):
            flush()
            current_subsection = line.lstrip("# ").strip()
            current_content = []
        else:
            current_content.append(line)

    flush()

    if not chunks and body.strip():
        content = body.strip()
        chunk_id = _chunk_id(file_path, "full document", 0, content)
        chunks.append(
            VaultChunk(
                chunk_id=chunk_id,
                file_path=file_path,
                heading="full document",
                content=content,
                tags=tags,
            )
        )

    return chunks


def _split_frontmatter(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}, match.group(2)
    if not isinstance(metadata, dict):
        return {}, match.group(2)
    return metadata, match.group(2)


def _extract_tags(frontmatter: dict) -> tuple[str, ...]:
    raw = frontmatter.get("tags", [])
    if isinstance(raw, list):
        return tuple(str(tag) for tag in raw)
    if isinstance(raw, str):
        return tuple(t.strip() for t in raw.split(",") if t.strip())
    return ()


def _chunk_id(file_path: str, heading: str, index: int, content: str) -> str:
    digest_input = f"{file_path}:{heading}:{index}:{content[:100]}".encode()
    return hashlib.md5(digest_input).hexdigest()
