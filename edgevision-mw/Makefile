.PHONY: dev test migrate seed logs lint format clean shell

# ─── Development ────────────────────────────────────────────────────────────

dev:
	POSTGRES_HOST=localhost uvicorn app.main:app --reload --port 8000

dev-worker:
	INSTALL_TRAINING_DEPS=true celery -A app.workers.celery_app worker --loglevel=info --concurrency=4

dev-beat:
	INSTALL_TRAINING_DEPS=true celery -A app.workers.celery_app beat --loglevel=info

shell:
	POSTGRES_HOST=localhost python -c "import asyncio; from app.core.database import async_session; loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); db = loop.run_until_complete(async_session().__aenter__()); print('db session ready')"

# ─── Testing ────────────────────────────────────────────────────────────────

test:
	POSTGRES_HOST=localhost python -m pytest tests/ -v

test-cov:
	POSTGRES_HOST=localhost python -m pytest tests/ --cov=app --cov-report=term-missing

test-file:
	POSTGRES_HOST=localhost python -m pytest tests/$(f) -v

# ─── Database ───────────────────────────────────────────────────────────────

migrate:
	alembic upgrade head

migrate-downgrade:
	alembic downgrade -1

migration:
	alembic revision --autogenerate -m "$(m)"

seed:
	POSTGRES_HOST=localhost python scripts/seed.py

# ─── Docker ─────────────────────────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

logs-app:
	docker compose logs -f app

logs-worker:
	docker compose logs -f celery_worker

restart:
	docker compose restart

build:
	docker compose build

# ─── Lint / Format ──────────────────────────────────────────────────────────

lint:
	ruff check app/ tests/

lint-fix:
	ruff check --fix app/ tests/

format:
	ruff format app/ tests/

format-check:
	ruff format --check app/ tests/

typecheck:
	python -m mypy app/

# ─── Cleanup ────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache

# ─── CI Check (runs everything) ─────────────────────────────────────────────

ci-check: lint format-check typecheck test
