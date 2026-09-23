# AI QA Platform — Production Operations & Monitoring

This document details day-to-day operations, observability, Prometheus metrics scraping, alerting rules, and incident runbooks for the AI QA Platform.

---

## 1. Observability & Prometheus Metrics

The AI QA API exposes a standard Prometheus exposition endpoint at `GET /api/metrics`.

### Core Metrics Exported:

| Metric Name | Type | Description |
|---|---|---|
| `ai_qa_platform_uptime_seconds` | Gauge | Platform API uptime in seconds |
| `ai_qa_workers_total` | Gauge | Total registered distributed runner nodes |
| `ai_qa_workers_online` | Gauge | Number of healthy online runner nodes |
| `ai_qa_workers_busy` | Gauge | Number of workers actively executing tests |
| `ai_qa_jobs_status{state="queued|running|completed|failed"}` | Gauge | Distributed job queue depth partitioned by state |
| `ai_qa_test_runs_total` | Counter | Total test suite executions recorded |
| `ai_qa_http_requests_total{method, path, status}` | Counter | Inbound API requests by method, route, and status |

### Prometheus Scrape Config Example:

```yaml
scrape_configs:
  - job_name: 'ai-qa-platform'
    scrape_interval: 15s
    metrics_path: '/api/metrics'
    static_configs:
      - targets: ['api:8000']
```

---

## 2. Recommended Alerting Thresholds

| Alert Rule | Condition | Severity | Action |
|---|---|---|---|
| `QueueBacklogHigh` | `ai_qa_jobs_status{state="queued"} > 20 for 5m` | Warning | Scale worker node replicas |
| `NoWorkersOnline` | `ai_qa_workers_online == 0 for 2m` | Critical | Inspect worker container crash logs |
| `ApiDegraded` | `rate(ai_qa_http_requests_total{status=~"5.."}[5m]) > 0.05` | Critical | Check database connectivity & API logs |
| `WorkerLost` | `(ai_qa_workers_total - ai_qa_workers_online) > 0 for 10m` | Warning | Auto-quarantine will clean up stale nodes |

---

## 3. Log Aggregation & Logging Standard

- Application logs follow structured ISO8601 formatting: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.
- Centralize logs into Loki, Datadog, or CloudWatch via container stdout/stderr.

---

## 4. Runbooks

### Runbook A: Worker Capacity Shortage
1. Check queue status: `GET /api/workers/cluster-status`.
2. Check unassigned jobs: `GET /api/jobs?status=queued`.
3. Scale worker nodes:
   ```bash
   docker compose up -d --scale worker=5
   ```
4. Verify new workers registered within 15 seconds.

### Runbook B: Database Connection Exhaustion
1. Check active database sessions in PostgreSQL:
   ```sql
   SELECT count(*), state FROM pg_stat_activity GROUP BY state;
   ```
2. Verify pool settings in `apps/api/app/persistence/database.py` (default: 20 connections + 10 overflow).
3. Restart API instances gracefully if connections leaked.
