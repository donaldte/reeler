.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down build logs shell manage migrate makemigrations superuser \
        test lint format typecheck check pre-commit-install ollama-pull \
        tailwind-install tailwind-build tailwind-watch worker-logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start the full dev stack (db, redis, ollama, web, worker)
	$(COMPOSE) up -d

down: ## Stop the dev stack
	$(COMPOSE) down

build: ## Rebuild the web/worker images
	$(COMPOSE) build

logs: ## Tail web logs
	$(COMPOSE) logs -f web

worker-logs: ## Tail worker logs
	$(COMPOSE) logs -f worker

shell: ## Open a Django shell inside the web container
	$(COMPOSE) exec web python manage.py shell

manage: ## Run an arbitrary management command: make manage ARGS="createsuperuser"
	$(COMPOSE) exec web python manage.py $(ARGS)

migrate: ## Apply database migrations
	$(COMPOSE) exec web python manage.py migrate

makemigrations: ## Generate new migrations
	$(COMPOSE) exec web python manage.py makemigrations

superuser: ## Create a Django admin superuser
	$(COMPOSE) exec web python manage.py createsuperuser

ollama-pull: ## Pull the configured Ollama model (run once after first `make up`)
	$(COMPOSE) exec ollama ollama pull $${OLLAMA_MODEL:-qwen2.5:3b}

test: ## Run the test suite with coverage
	uv run pytest

lint: ## Lint with ruff
	uv run ruff check .

format: ## Auto-format with ruff
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Type-check with mypy
	uv run mypy .

check: lint typecheck test ## Run lint + typecheck + test (what CI runs)

pre-commit-install: ## Install git pre-commit hooks
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg

tailwind-install: ## Download the standalone Tailwind CLI into bin/
	./scripts/install_tailwind.sh

tailwind-build: ## Build static/css/output.css (minified, one-shot)
	./bin/tailwindcss -i static/css/input.css -o static/css/output.css --minify

tailwind-watch: ## Rebuild static/css/output.css on change
	./bin/tailwindcss -i static/css/input.css -o static/css/output.css --watch

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml staticfiles
