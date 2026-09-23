# AI QA Platform — Backup & Disaster Recovery Guide

This document defines backup strategies, retention policies, and disaster recovery procedures for database state and artifact storage.

---

## 1. Backup Strategy Overview

The platform stores two types of persistent state:
1. **Relational Database (PostgreSQL / SQLite)**: Requirements, Test Designs, Test Cases, Quality Risks, Releases, RBAC Users/Teams, Security Audit Trails, Run Histories.
2. **Object Storage (MinIO / S3)**: Playwright execution traces, screenshots, DOM snapshots, Allure reports, and failure artifacts.

---

## 2. Automated Database Backup Tool

Use the built-in backup script:

```bash
# Perform automated backup with gzip compression and timestamp
./scripts/backup_db.sh ./runtime/backups
```

### Cron Job Automation
Set up a daily cron job at 02:00 UTC:

```bash
0 2 * * * cd /opt/ai-qa-platform && ./scripts/backup_db.sh /var/backups/aiqa >> /var/log/aiqa_backup.log 2>&1
```

The script automatically:
- Connects to PostgreSQL via `pg_dump` or Docker container.
- Compresses the dump with gzip (`.sql.gz`).
- Rotates old backups retaining the latest 10 versions.

---

## 3. Database Restoration Procedure

In the event of data corruption or disaster recovery:

```bash
# 1. Stop active worker and API traffic
docker compose stop api worker

# 2. Execute restore script
./scripts/restore_db.sh ./runtime/backups/aiqa_postgres_20260923_100000.sql.gz

# 3. Restart services
docker compose start api worker

# 4. Verify system health
./scripts/prod_smoke_test.sh
```

---

## 4. Artifact Storage Replication & Backup

For MinIO / S3 object storage:
- **AWS S3 / GCS**: Enable Cross-Region Replication (CRR) and Object Versioning.
- **Self-Hosted MinIO**: Use `mc mirror` to continuously mirror `local/ai-qa-artifacts` to secondary remote storage:
  ```bash
  mc mirror --watch local/ai-qa-artifacts backup-s3/ai-qa-artifacts-dr
  ```
