# Coding Standards

## Style & formatting

Enforced by `ruff` (lint + format + import sorting) and `mypy`, run via
pre-commit and CI (`make check` runs the same checks locally).

- Line length 100.
- Full type hints on function signatures (`mypy` runs with
  `disallow_untyped_defs`). Use `domain/`'s dataclasses/DTOs to move typed
  data across the `domain`/`apps` boundary rather than passing dicts.
- Prefer `pathlib.Path` over string paths.
- Docstrings explain *why*, not *what* — the code already says what;
  reserve comments/docstrings for rationale, trade-offs, and things a
  reader would otherwise have to reconstruct from git history (see the
  existing modules for the tone we're going for).

## Architecture rules (enforced by convention, not tooling — please respect them in review)

- `domain/` must never import Django (`django.*`). If you find yourself
  needing `django.conf.settings` inside `domain/`, pass the values in as
  function arguments instead (see `domain/ai/registry.py`).
- `apps/*/tasks.py` should stay thin: call into `domain/`, map the result
  onto models, update pipeline status. Business logic (prompt construction,
  retry/repair flows, media parsing) belongs in `domain/`.
- New AI capabilities/providers follow the pattern in
  [docs/ai_pipeline.md](ai_pipeline.md) — ABC in `domain/<capability>/base.py`,
  implementation in `domain/<capability>/providers/`, registered in
  `domain/ai/registry.py`.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`,
`fix:`, `docs:`, `refactor:`, `test:`, `chore:`, etc. Enforced by the
`commitizen` pre-commit hook once you've run `make pre-commit-install`.
Versioning follows [SemVer](https://semver.org/); `CHANGELOG.md` follows
[Keep a Changelog](https://keepachangelog.com/).

## Tests

- New `domain/` code: unit tests with every external boundary mocked
  (`subprocess`, `httpx`) — see `domain/tests/` for the pattern.
- New Celery tasks: test the task function directly (Celery tasks are
  plain callables), mocking the `domain/` calls — see
  `apps/*/tests/test_tasks.py`.
- Changes touching the full pipeline: extend
  `apps/videos/tests/test_pipeline_integration.py` rather than writing a
  new end-to-end test from scratch.
- Run `make test` (or `uv run pytest`) before opening a PR.
