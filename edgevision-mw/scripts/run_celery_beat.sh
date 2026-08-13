#!/usr/bin/env bash
# Run Celery beat scheduler for local development
# Usage: ./scripts/run_celery_beat.sh
set -euo pipefail

if [ -f .venv/bin/activate ]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

export INSTALL_TRAINING_DEPS=true
export POSTGRES_HOST=localhost

celery -A app.workers.celery_app beat --loglevel=info
