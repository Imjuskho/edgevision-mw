#!/usr/bin/env bash
# =============================================================================
# EdgeVision-MW — Backup Script
# Backs up PostgreSQL, Redis, and MinIO data to a timestamped directory.
#
# Usage:
#   ./scripts/backup.sh                    # uses defaults
#   ./scripts/backup.sh /mnt/backup-pool   # custom backup directory
#
# Requires: docker, pg_dump (optional, for local pg_dump fallback)
# Schedule via cron: 0 2 * * * /path/to/scripts/backup.sh /mnt/backups >> /var/log/edgevision-backup.log 2>&1
# =============================================================================

set -euo pipefail

BACKUP_ROOT="${1:-/mnt/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/edgevision_${TIMESTAMP}"
RETENTION_DAYS=30

COMPOSE_PROJECT="edgevision"
PG_CONTAINER="edgevision-postgres-1"
REDIS_CONTAINER="edgevision-redis-1"
MINIO_CONTAINER="edgevision-minio-1"

PG_USER="${POSTGRES_USER:-edgevision}"
PG_DB="${POSTGRES_DB:-edgevision_mw}"
PG_PASSWORD="${POSTGRES_PASSWORD:-edgevision_secret}"

MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
MINIO_BUCKET="${MINIO_BUCKET:-edgevision-data-lake}"

echo "[backup] Starting EdgeVision-MW backup → ${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}/postgres" "${BACKUP_DIR}/redis" "${BACKUP_DIR}/minio"

# ─── PostgreSQL ─────────────────────────────────────────────────────────────
echo "[backup] Dumping PostgreSQL (${PG_DB})..."
docker exec "${PG_CONTAINER}" \
  pg_dump -U "${PG_USER}" -d "${PG_DB}" --no-owner --no-acl \
  | gzip > "${BACKUP_DIR}/postgres/${PG_DB}.sql.gz"

echo "[backup] Backing up PostgreSQL globals..."
docker exec "${PG_CONTAINER}" \
  pg_dumpall -U "${PG_USER}" --globals-only \
  | gzip > "${BACKUP_DIR}/postgres/globals.sql.gz"

PG_SIZE=$(du -sh "${BACKUP_DIR}/postgres" | cut -f1)
echo "[backup] PostgreSQL dump: ${PG_SIZE}"

# ─── Redis ──────────────────────────────────────────────────────────────────
echo "[backup] Backing up Redis (BGSAVE + copy)..."
docker exec "${REDIS_CONTAINER}" redis-cli -a "${REDIS_PASSWORD}" BGSAVE >/dev/null 2>&1
sleep 2
docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "${BACKUP_DIR}/redis/dump.rdb" 2>/dev/null || \
  echo "[backup] Warning: Redis dump.rdb not found (BGSAVE may still be running)"

REDIS_SIZE=$(du -sh "${BACKUP_DIR}/redis" 2>/dev/null | cut -f1 || echo "0")
echo "[backup] Redis backup: ${REDIS_SIZE}"

# ─── MinIO ──────────────────────────────────────────────────────────────────
echo "[backup] Backing up MinIO data (mc mirror)..."
# Use mc (MinIO client) if available, otherwise copy the volume directly
if command -v mc &>/dev/null; then
  mc alias set edgevision-backup "http://localhost:9000" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" >/dev/null 2>&1
  mc mirror --overwrite "edgevision-backup/${MINIO_BUCKET}" "${BACKUP_DIR}/minio/${MINIO_BUCKET}" >/dev/null 2>&1
  mc alias rm edgevision-backup >/dev/null 2>&1
else
  # Fallback: copy from the Docker volume
  docker cp "${MINIO_CONTAINER}:/data/" "${BACKUP_DIR}/minio/data/" 2>/dev/null || \
    echo "[backup] Warning: MinIO data copy failed"
fi

MINIO_SIZE=$(du -sh "${BACKUP_DIR}/minio" 2>/dev/null | cut -f1 || echo "0")
echo "[backup] MinIO backup: ${MINIO_SIZE}"

# ─── Metadata ───────────────────────────────────────────────────────────────
cat > "${BACKUP_DIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "postgres_db": "${PG_DB}",
  "postgres_size": "${PG_SIZE}",
  "redis_size": "${REDIS_SIZE}",
  "minio_size": "${MINIO_SIZE}",
  "retention_days": ${RETENTION_DAYS}
}
EOF

TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
echo "[backup] Complete: ${BACKUP_DIR} (${TOTAL_SIZE})"

# ─── Cleanup old backups ────────────────────────────────────────────────────
echo "[backup] Cleaning backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_ROOT}" -maxdepth 1 -name "edgevision_*" -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} \; 2>/dev/null || true

echo "[backup] Done."
