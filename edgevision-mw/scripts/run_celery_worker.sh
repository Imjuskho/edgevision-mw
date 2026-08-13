#!/usr/bin/env bash
# Run a Celery worker for local development
# Usage: ./scripts/run_celery_worker.sh
set -euo pipefail

# Activate venv if present
if [ -f .venv/bin/activate ]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

export INSTALL_TRAINING_DEPS=true
export POSTGRES_HOST=localhost

celery -A app.workers.celery_app worker --loglevel=info --concurrency=4
