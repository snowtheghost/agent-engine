import argparse
import asyncio
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-engine",
        description="Provider-agnostic runtime for AI agents with per-project persistent knowledge.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Project directory. Defaults to current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start all enabled intakes and block.")
    serve.add_argument(
        "--no-discord",
        action="store_true",
        help="Disable the Discord intake for this run.",
    )
    serve.add_argument(
        "--no-http",
        action="store_true",
        help="Disable the HTTP intake for this run.",
    )

    run = subparsers.add_parser("run", help="Dispatch a single prompt and print the summary.")
    run.add_argument("--prompt", required=True, help="Prompt to send to the agent.")
    run.add_argument("--resume-key", default=None, help="Optional resume key.")
    run.add_argument("--model", default=None, help="Model override.")

    vault = subparsers.add_parser("vault", help="Vault operations.")
    vault_sub = vault.add_subparsers(dest="vault_command", required=True)

    vault_search = vault_sub.add_parser("search", help="Semantic search the vault.")
    vault_search.add_argument("query")
    vault_search.add_argument("--limit", type=int, default=5)

    vault_list = vault_sub.add_parser("list", help="List recent vault entries.")
    vault_list.add_argument("--limit", type=int, default=20)

    vault_recall = vault_sub.add_parser("recall", help="Show a specific entry.")
    vault_recall.add_argument("entry_id")

    return parser


async def _run_serve(cwd: Path, no_discord: bool, no_http: bool) -> int:
    from agent_engine.main import run_engine

    await run_engine(cwd=cwd, disable_discord=no_discord, disable_http=no_http)
    return 0


async def _run_prompt(cwd: Path, prompt: str, resume_key: str | None, model: str | None) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd)
    try:
        result = await engine.run_service.dispatch(
            prompt, resume_key=resume_key, model=model
        )
        print(result.summary)
        if not result.success:
            sys.stderr.write(f"\n[error] {result.error}\n")
            return 1
        return 0
    finally:
        shutdown_engine(engine)


def _run_vault_search(cwd: Path, query: str, limit: int) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd)
    try:
        hits = engine.vault_service.search(query, limit)
        if not hits:
            print("No results.")
            return 0
        for hit in hits:
            tags = ", ".join(hit.entry.tags) if hit.entry.tags else "-"
            print(f"[{hit.score:.3f}] {hit.entry.entry_id}  {hit.entry.kind}  {hit.entry.title}")
            print(f"    tags: {tags}")
            preview = hit.entry.body.replace("\n", " ")[:200]
            print(f"    {preview}")
            print()
        return 0
    finally:
        shutdown_engine(engine)


def _run_vault_list(cwd: Path, limit: int) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd)
    try:
        entries = engine.vault_service.list(limit)
        if not entries:
            print("Vault is empty.")
            return 0
        for entry in entries:
            print(f"{entry.entry_id}  {entry.kind}  {entry.title}")
        return 0
    finally:
        shutdown_engine(engine)


def _run_vault_recall(cwd: Path, entry_id: str) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd)
    try:
        entry = engine.vault_service.recall(entry_id)
        if entry is None:
            sys.stderr.write(f"No entry with id {entry_id}\n")
            return 1
        print(f"Entry   : {entry.entry_id}")
        print(f"Kind    : {entry.kind}")
        print(f"Title   : {entry.title}")
        print(f"Tags    : {', '.join(entry.tags) if entry.tags else '-'}")
        print(f"Created : {entry.created_at.isoformat()}")
        print()
        print(entry.body)
        return 0
    finally:
        shutdown_engine(engine)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cwd = args.cwd.resolve()

    if args.command == "serve":
        return asyncio.run(_run_serve(cwd, args.no_discord, args.no_http))
    if args.command == "run":
        return asyncio.run(_run_prompt(cwd, args.prompt, args.resume_key, args.model))
    if args.command == "vault":
        if args.vault_command == "search":
            return _run_vault_search(cwd, args.query, args.limit)
        if args.vault_command == "list":
            return _run_vault_list(cwd, args.limit)
        if args.vault_command == "recall":
            return _run_vault_recall(cwd, args.entry_id)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
