# Contributing

Thanks for the interest.

## Development setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Running tests

```bash
pytest
```

All tests use the in-memory vector index by default — no heavy model downloads in CI.

## Code style

- Python 3.13+, clean domain-driven design.
- `core` is pure (no I/O, no logging). `application` defines Protocols/ABCs. `infrastructure` / `providers` / `integrations` implement them.
- Explicit types on every signature and return.
- Self-documenting names; no comments or docstrings in new code.
- Tests mirror source structure under `tests/`.
- `ruff check .` before sending a PR.

## Adding a provider

Implement `Runner` at `application/run/runner/runner.py`, drop the files under `providers/<name>/`, register in `main._build_runner`. That's it.

## Adding an integration

Implement `Intake` at `application/integration/intake.py`, drop the files under `integrations/<name>/`, register in `main._build_intakes`.

## Keeping `SPECIFICATION.md` current

`SPECIFICATION.md` is the rebuild contract. Any structural change to the engine must update it in the same PR.
