---
description: Search the vault for facts, decisions, architecture notes, and any durable knowledge. Use before answering questions about the project, before starting work on a topic, or when you need to know what was decided before.
---

# /recall

Search the project vault semantically. Use early and often — before claims, before starting work, before answering.

## Steps

1. **Search.** Call `vault_search(query="<topic>", limit=5)`. The query is natural language; the index is embedding-based, so paraphrases work.
   - Narrow scope with `file="<path-substring>"` when you already know where to look.
   - Raise `limit` to 10 for exploratory queries.

2. **Read the top hits.** Each result has `file_path`, `heading`, preview, and `score`. Higher score = more semantically relevant. For anything above ~0.6, open the file with `vault_recall(path=<file_path>)` for full context; snippets are chunks, not complete answers.

3. **Triangulate.** One hit is a lead, not a conclusion. Run a second search with a different phrasing or a related concept to check coverage. Scan `Index.md` if you are unsure what exists.

## Rules

- Never assert something "isn't in the vault" without searching.
- Never paraphrase a vault hit as your own knowledge — attribute it to the file.
- If the vault contradicts what you were about to say, stop and reconsider.
- Scores are relative within a query, not absolute. Compare hits to each other, not to a threshold.
