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
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Data directory for config, vault DB, and sessions. Defaults to ~/.agent-engine/.",
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
    vault_search.add_argument("--file", default=None)

    vault_recall = vault_sub.add_parser("recall", help="Show a vault file by path.")
    vault_recall.add_argument("path")

    vault_sub.add_parser("list", help="List indexed vault file paths.")

    return parser


async def _run_serve(cwd: Path, data_dir: Path | None, no_discord: bool, no_http: bool) -> int:
    from agent_engine.main import run_engine

    await run_engine(cwd=cwd, data_dir=data_dir, disable_discord=no_discord, disable_http=no_http)
    return 0


async def _run_prompt(
    cwd: Path, data_dir: Path | None, prompt: str, resume_key: str | None, model: str | None
) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd, data_dir=data_dir)
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


def _run_vault_search(
    cwd: Path,
    data_dir: Path | None,
    query: str,
    limit: int,
    file_filter: str | None,
) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd, data_dir=data_dir)
    try:
        hits = engine.vault_service.search(query, limit, file_filter=file_filter)
        if not hits:
            print("No results.")
            return 0
        for hit in hits:
            tags = ", ".join(hit.chunk.tags) if hit.chunk.tags else "-"
            print(f"[{hit.score:.3f}] {hit.chunk.file_path}  ({hit.chunk.heading})")
            print(f"    tags: {tags}")
            preview = hit.chunk.content.replace("\n", " ")[:240]
            print(f"    {preview}")
            print()
        return 0
    finally:
        shutdown_engine(engine)


def _run_vault_list(cwd: Path, data_dir: Path | None) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd, data_dir=data_dir)
    try:
        paths = sorted(engine.vault_service.files())
        if not paths:
            print("Vault is empty.")
            return 0
        for path in paths:
            print(path)
        return 0
    finally:
        shutdown_engine(engine)


def _run_vault_recall(cwd: Path, data_dir: Path | None, path: str) -> int:
    from agent_engine.main import build_engine, shutdown_engine

    engine = build_engine(cwd=cwd, data_dir=data_dir)
    try:
        body = engine.vault_service.recall(path)
        if body is None:
            sys.stderr.write(f"No vault file at {path}\n")
            return 1
        print(body)
        return 0
    finally:
        shutdown_engine(engine)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cwd = args.cwd.resolve()
    data_dir = args.data_dir.resolve() if args.data_dir else None

    if args.command == "serve":
        return asyncio.run(_run_serve(cwd, data_dir, args.no_discord, args.no_http))
    if args.command == "run":
        return asyncio.run(_run_prompt(cwd, data_dir, args.prompt, args.resume_key, args.model))
    if args.command == "vault":
        if args.vault_command == "search":
            return _run_vault_search(cwd, data_dir, args.query, args.limit, args.file)
        if args.vault_command == "list":
            return _run_vault_list(cwd, data_dir)
        if args.vault_command == "recall":
            return _run_vault_recall(cwd, data_dir, args.path)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
