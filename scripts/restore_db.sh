#!/usr/bin/env bash
set -euo pipefail

# AI QA Platform — Database Restore Utility
# Usage: ./scripts/restore_db.sh <backup_file.gz> [target_db]
#
# Restoring overwrites the live database, so an existing target is snapshotted to
# <target_db>.pre-restore.<timestamp> first (the restore is itself the rollback path).

if [ $# -lt 1 ]; then
    echo "Usage: $0 <path_to_backup_file.gz> [target_db]"
    exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-./runtime/ai_qa_platform.db}"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file '$BACKUP_FILE' does not exist."
    exit 1
fi

echo "=== AI QA Platform: Database Restore ==="
echo "Source Backup: $BACKUP_FILE"

if [[ "$BACKUP_FILE" == *"postgres"* ]]; then
    echo "Restoring PostgreSQL database..."
    if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
        gunzip -c "$BACKUP_FILE" | psql "$DATABASE_URL"
    else
        echo "Using docker compose to restore into aiqa-postgres..."
        gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-aiqa}" -d "${POSTGRES_DB:-ai_qa_platform}"
    fi
    echo "PostgreSQL database restored successfully."
else
    echo "Restoring SQLite database..."
    mkdir -p "$(dirname "$TARGET_DB")"
    if [ -f "$TARGET_DB" ]; then
        SNAPSHOT="${TARGET_DB}.pre-restore.$(date +"%Y%m%d_%H%M%S")"
        cp "$TARGET_DB" "$SNAPSHOT"
        echo "Existing database snapshotted to $SNAPSHOT"
    fi
    gunzip -c "$BACKUP_FILE" > "$TARGET_DB"
    echo "SQLite database restored successfully to $TARGET_DB."
fi

echo "Database restore completed successfully."
