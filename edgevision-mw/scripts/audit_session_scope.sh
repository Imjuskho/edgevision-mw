#!/bin/bash
# Find all functions that commit then verify with a new session
# Usage: bash scripts/audit_session_scope.sh

echo "=== Searching for commit-then-verify anti-pattern ==="
MISES=0

while IFS= read -r line; do
    file=$(echo "$line" | cut -d: -f1)
    linenum=$(echo "$line" | cut -d: -f2)
    context=$(tail -n +"$linenum" "$file" | head -n 15)
    if echo "$context" | grep -qE 'get_db\(\)|async_session\(\)|async_session\('; then
        echo "SUSPECT: $file:$linenum"
        MISES=$((MISES + 1))
    fi
done < <(grep -rn "await db.commit()" app/ --include="*.py")

if [ "$MISES" -eq 0 ]; then
    echo "PASS: No commit-then-verify anti-patterns found"
else
    echo "FOUND: $MISES suspect patterns — review each"
fi
