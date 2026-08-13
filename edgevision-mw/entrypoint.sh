#!/bin/sh
set -e

echo "edgevision-mw: waiting for postgres..."
until pg_isready -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-edgevision}" -d "${POSTGRES_DB:-edgevision_mw}" -q; do
  sleep 1
done
echo "edgevision-mw: postgres ready"

echo "edgevision-mw: running alembic migrations..."
alembic upgrade head

echo "edgevision-mw: starting uvicorn...${*:+ extra args: $*}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
