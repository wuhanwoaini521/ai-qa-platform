#!/usr/bin/env bash
set -euo pipefail

# AI QA Platform — Database Backup Utility
# Usage: ./scripts/backup_db.sh [output_dir]

BACKUP_DIR="${1:-./runtime/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"

echo "=== AI QA Platform: Database Backup ==="
echo "Timestamp: $TIMESTAMP"
echo "Target Directory: $BACKUP_DIR"

if [ -n "${DATABASE_URL:-}" ] && [[ "$DATABASE_URL" == postgresql* ]]; then
    echo "Detected PostgreSQL database."
    BACKUP_FILE="${BACKUP_DIR}/aiqa_postgres_${TIMESTAMP}.sql.gz"
    
    # Check for pg_dump or docker compose
    if command -v pg_dump >/dev/null 2>&1; then
        pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
    else
        echo "Using docker compose to execute pg_dump inside aiqa-postgres..."
        docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-aiqa}" "${POSTGRES_DB:-ai_qa_platform}" | gzip > "$BACKUP_FILE"
    fi
    echo "PostgreSQL backup created successfully: $BACKUP_FILE"
else
    echo "Backing up local SQLite database..."
    SQLITE_DB="./runtime/ai_qa_platform.db"
    BACKUP_FILE="${BACKUP_DIR}/aiqa_sqlite_${TIMESTAMP}.db.gz"

    if [ -f "$SQLITE_DB" ]; then
        # The database runs in WAL mode, so copying the file alone can miss committed
        # transactions still in the write-ahead log. Snapshot it through SQLite's online
        # backup API first.
        SNAPSHOT="$(mktemp "${TMPDIR:-/tmp}/aiqa_sqlite_backup.XXXXXX.db")"
        "${AI_QA_PYTHON:-python3}" - "$SQLITE_DB" "$SNAPSHOT" <<'PY'
import sqlite3, sys

source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
with target:
    source.backup(target)
target.close()
source.close()
PY
        gzip -c "$SNAPSHOT" > "$BACKUP_FILE"
        rm -f "$SNAPSHOT"
        echo "SQLite backup created successfully: $BACKUP_FILE"
    else
        echo "Warning: SQLite database file not found at $SQLITE_DB. Creating empty marker backup."
        gzip -c <(echo "empty database marker") > "$BACKUP_FILE"
    fi
fi

# Rotate backups keeping latest 10
echo "Rotating old backups (retaining latest 10)..."
find "$BACKUP_DIR" -name "aiqa_*.gz" -type f | sort -r | tail -n +11 | xargs -r rm -f || true

echo "Backup complete! Backup file: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
