# Contributing to Reeler

Thanks for considering a contribution! This is an early-stage project — see
[docs/roadmap.md](docs/roadmap.md) and [docs/backlog.md](docs/backlog.md)
for where help is most useful.

## Getting set up

Follow [docs/quickstart.md](docs/quickstart.md), then
[docs/development.md](docs/development.md) for the day-to-day workflow.

## Before you start

- For anything beyond a small fix, open an issue first (or comment on an
  existing one) describing what you plan to do — saves everyone rework if
  the approach needs discussion. Use the feature request template for new
  capabilities, especially ones touching the AI pipeline (see
  [docs/ai_pipeline.md](docs/ai_pipeline.md) for the provider architecture
  new AI capabilities should follow).
- Check [docs/architecture.md](docs/architecture.md) and
  [docs/coding_standards.md](docs/coding_standards.md) first — Reeler
  follows a fairly strict layering convention (`domain/` vs `apps/`) that's
  easy to violate by accident.

## Making changes

1. Fork and branch from `main`.
2. Make your change, with tests — see the testing section in
   [docs/coding_standards.md](docs/coding_standards.md).
3. `make check` (ruff + mypy + pytest) — this is what CI runs.
4. Commit using [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, ...).
   `make pre-commit-install` sets up a commit-msg hook that enforces this.
5. Open a PR against `main`, filling out the PR template. Link the issue it
   closes.

## Code review

Expect review comments focused on: does this respect the `domain`/`apps`
layering, is it tested, does it match the existing patterns for its kind of
change (new provider, new app, new Celery task, ...). See
[docs/architecture.md](docs/architecture.md) for what "the existing
pattern" means concretely.

## Reporting bugs / requesting features

Use the GitHub issue templates (bug report / feature request) — they ask
for the context that's usually needed to act on an issue quickly.

## Code of conduct

Be respectful and constructive. This project doesn't yet have a formal
Code of Conduct document — if you'd like to help draft one (e.g. adopting
the [Contributor Covenant](https://www.contributor-covenant.org/)), please
open an issue.
