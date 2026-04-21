from agent_engine.infrastructure.vault.chunker import chunk_markdown


def test_chunks_split_on_h2_headings():
    text = (
        "# Document\n"
        "\n"
        "## Section A\n"
        "Content about authentication and oauth flows.\n"
        "\n"
        "## Section B\n"
        "Content about databases and migrations.\n"
    )
    chunks = chunk_markdown(text, "notes.md")
    headings = [c.heading for c in chunks]
    assert "Section A" in headings
    assert "Section B" in headings


def test_chunks_split_on_h3_subsections():
    text = (
        "## Parent\n"
        "Parent intro text long enough to pass the minimum content threshold.\n"
        "\n"
        "### Child A\n"
        "Child A content about oauth and sessions.\n"
        "\n"
        "### Child B\n"
        "Child B content about databases and indexes.\n"
    )
    chunks = chunk_markdown(text, "notes.md")
    headings = [c.heading for c in chunks]
    assert "Child A" in headings
    assert "Child B" in headings


def test_frontmatter_tags_propagate_to_chunks():
    text = (
        "---\n"
        "tags: [identity, mind]\n"
        "---\n"
        "\n"
        "## Intro\n"
        "Body content long enough to be chunked into a section here.\n"
    )
    chunks = chunk_markdown(text, "a.md")
    assert chunks
    assert chunks[0].tags == ("identity", "mind")


def test_short_sections_below_threshold_are_skipped():
    text = (
        "## too short\n"
        "hi\n"
        "\n"
        "## long enough\n"
        "this section has more than twenty characters so survives the filter\n"
    )
    chunks = chunk_markdown(text, "x.md")
    headings = [c.heading for c in chunks]
    assert "long enough" in headings
    assert "too short" not in headings


def test_single_chunk_for_file_without_headings():
    text = (
        "---\n"
        "tags: []\n"
        "---\n"
        "\n"
        "This is a short note with no markdown headings in it. Long enough to pass.\n"
    )
    chunks = chunk_markdown(text, "loose.md")
    assert len(chunks) == 1
    assert "no markdown headings" in chunks[0].content


def test_chunk_ids_are_deterministic_per_file_heading_and_position():
    text = "## S\nThis is a section body long enough to count as a chunk.\n"
    first = chunk_markdown(text, "a.md")
    second = chunk_markdown(text, "a.md")
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_chunk_ids_differ_across_files():
    text = "## S\nThis is a section body long enough to count as a chunk.\n"
    a = chunk_markdown(text, "a.md")[0]
    b = chunk_markdown(text, "b.md")[0]
    assert a.chunk_id != b.chunk_id
