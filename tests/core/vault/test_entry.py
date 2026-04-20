from datetime import datetime, timezone
from pathlib import Path

from agent_engine.core.vault.model.entry import VaultEntry, VaultSearchHit


def test_entry_frozen():
    entry = VaultEntry(
        entry_id="e1",
        kind="decision",
        title="Use WAL",
        body="WAL mode chosen for concurrency.",
        tags=("sqlite", "perf"),
        created_at=datetime.now(timezone.utc),
    )
    assert entry.tags == ("sqlite", "perf")


def test_search_hit_carries_score_and_path():
    entry = VaultEntry(
        entry_id="e1",
        kind="note",
        title="x",
        body="y",
        tags=(),
        created_at=datetime.now(timezone.utc),
    )
    hit = VaultSearchHit(entry=entry, score=0.42, path=Path("/tmp/e1.md"))
    assert hit.score == 0.42
    assert hit.path == Path("/tmp/e1.md")
