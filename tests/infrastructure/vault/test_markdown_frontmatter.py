from datetime import datetime, timezone

from agent_engine.core.vault.model.entry import VaultEntry
from agent_engine.infrastructure.vault.markdown_frontmatter import format_entry, parse_entry


def _entry(**overrides) -> VaultEntry:
    defaults = dict(
        entry_id="abc",
        kind="note",
        title="Hello",
        body="Body text",
        tags=("a", "b"),
        created_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return VaultEntry(**defaults)


def test_format_roundtrips():
    entry = _entry()
    rendered = format_entry(entry)
    parsed = parse_entry(rendered)
    assert parsed == entry


def test_format_starts_with_frontmatter_block():
    rendered = format_entry(_entry())
    assert rendered.startswith("---\n")
    assert "\n---\n\n" in rendered


def test_parse_handles_empty_tags():
    entry = _entry(tags=())
    rendered = format_entry(entry)
    parsed = parse_entry(rendered)
    assert parsed.tags == ()


def test_parse_handles_multiline_body():
    body = "line one\n\nline two"
    entry = _entry(body=body)
    rendered = format_entry(entry)
    parsed = parse_entry(rendered)
    assert parsed.body == body


def test_parse_returns_none_when_no_frontmatter():
    assert parse_entry("just a body with no metadata") is None


def test_parse_returns_none_when_missing_required_fields():
    text = "---\nkind: note\n---\n\nbody\n"
    assert parse_entry(text) is None


def test_parse_accepts_tags_as_comma_string():
    text = (
        "---\n"
        "id: e1\n"
        "kind: note\n"
        "title: Hello\n"
        "tags: a, b, c\n"
        "created_at: 2026-01-01T00:00:00+00:00\n"
        "---\n"
        "\n"
        "body\n"
    )
    parsed = parse_entry(text)
    assert parsed is not None
    assert parsed.tags == ("a", "b", "c")
