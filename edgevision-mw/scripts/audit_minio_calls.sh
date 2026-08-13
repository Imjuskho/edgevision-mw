#!/bin/bash
# Audit MinIO call sites for direct usage outside wrapper
# Usage: bash scripts/audit_minio_calls.sh

echo "=== Raw MinIO client calls outside wrapper ==="
grep -rn "minio_client\." app/ --include="*.py" \
    | grep -v "app/core/minio.py" \
    | grep -v "test" \
    | grep -v ".pyc"

echo ""
echo "=== expires= with int literal (MinIO 7.x bug) ==="
grep -rn "expires=[0-9]" app/ --include="*.py" | grep -v test

echo ""
echo "=== get_object/fget_object/put_object calls (potentially missing .lstrip('/')) ==="
grep -rn "\.get_object\|\.fget_object\|\.put_object\|\.remove_object" app/ --include="*.py" \
    | grep -v test \
    | grep -v ".pyc"
