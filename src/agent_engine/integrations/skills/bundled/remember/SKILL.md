---
description: Save factual knowledge to the vault. Routes into the right directory, updates existing files rather than duplicating, and keeps the vault organized. Use for "remember", "save this", "record this", or any factual durable knowledge.
---

# /remember

Save factual knowledge to the project vault. Files on disk are the source of truth; the watcher re-indexes automatically.

## Steps

1. **Classify.** What kind of knowledge is this?
   - A durable fact about the project, a person, a system, a decision → vault.
   - A transient task, todo, or working note → NOT the vault. Keep it in the conversation.
   - A behavioral preference or correction → NOT the vault.

2. **Read the routing map.** Call `vault_recall(path="Index.md")` to see the vault's routing table and directory structure. If there is no `Index.md`, use `vault_search(query="index")` or list the directory with filesystem tools to understand the layout.

3. **Dedupe.** Call `vault_search(query="<topic>", limit=5)` to find existing files on the same topic.
   - If an existing file covers this topic, **update it** instead of writing a new one. Prefer Edit over vault_write.
   - If you find near-duplicates, note them and merge into one canonical file.
   - Only write a fresh file when no existing file fits.

4. **Write.**
   - Updating an existing file: use the `Edit` tool on the file at `{vault.directory}/{path}`. Add a new section or extend an existing one. Keep existing structure and frontmatter.
   - Creating a new file: use `vault_write(title, content, tags, subdirectory)`. `subdirectory` comes from the routing map. `tags` come from the topic. Structure the body with `## Section` headings so each section becomes its own searchable chunk.

5. **Confirm.** Report the path and whether you created or updated.

## Rules

- One file per topic. No `thing_1.md`, `thing_2.md`.
- Match existing file conventions (frontmatter tags, heading depth, table vs prose).
- Never fabricate content to pad a file. Write only what is factual.
- Never claim you remembered something without writing the file.
- Do not write into `.` (hidden) paths or outside the vault directory.
