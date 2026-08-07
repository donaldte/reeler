#!/usr/bin/env bash
# One-shot local dev setup: env file, Python deps, Tailwind CLI + build,
# pre-commit hooks. Does NOT start Docker services — run `make up` after.
# See docs/quickstart.md.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it before starting the stack."
fi

echo "==> uv sync"
uv sync

echo "==> Installing Tailwind CLI"
./scripts/install_tailwind.sh

echo "==> Building CSS"
./bin/tailwindcss -i static/css/input.css -o static/css/output.css --minify

echo "==> Installing pre-commit hooks"
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

cat <<'MSG'

Setup complete. Next steps:
  make up            # start db, redis, ollama, web, worker
  make migrate        # apply migrations
  make ollama-pull     # pull the default local LLM model
  make superuser        # create an admin login
Then visit http://localhost:8000
MSG
