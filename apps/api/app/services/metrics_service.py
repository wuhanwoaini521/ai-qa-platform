from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from app.persistence.database import async_session_factory
from app.repositories import JobRepository, TestRunRepository, WorkerRepository


class MetricsService:
    """Manages system metrics collection and Prometheus exposition formatting."""

    def __init__(self) -> None:
        self._start_time = time.time()
        self._http_requests_total: dict[str, int] = defaultdict(int)
        self._http_request_durations: dict[str, list[float]] = defaultdict(list)
        self._custom_counters: dict[str, int] = defaultdict(int)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def record_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        # Group generic paths to keep cardinality bounded
        normalized_path = self._normalize_path(path)
        key = f"{method}:{normalized_path}:{status_code}"
        self._http_requests_total[key] += 1

        # Track last 100 durations per key
        durations = self._http_request_durations[key]
        durations.append(duration_seconds)
        if len(durations) > 100:
            self._http_request_durations[key] = durations[-100:]

    def increment_counter(self, name: str, value: int = 1) -> None:
        self._custom_counters[name] += value

    def _normalize_path(self, path: str) -> str:
        # Collapse UUIDs/IDs into placeholder
        parts = path.split("/")
        normalized = []
        for part in parts:
            if not part:
                continue
            if len(part) >= 8 and ("-" in part or part.isdigit() or any(c.isdigit() for c in part)):
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/" + "/".join(normalized)

    async def get_summary_metrics(self) -> dict[str, Any]:
        async with async_session_factory() as session:
            worker_repo = WorkerRepository(session)
            job_repo = JobRepository(session)
            run_repo = TestRunRepository(session)

            workers = await worker_repo.list_all()
            online_workers = [w for w in workers if w.status in ("idle", "busy")]
            busy_workers = [w for w in workers if w.status == "busy"]

            jobs = await job_repo.list_jobs()
            queued_jobs = [j for j in jobs if j.status == "queued"]
            running_jobs = [j for j in jobs if j.status == "running"]
            completed_jobs = [j for j in jobs if j.status == "completed"]
            failed_jobs = [j for j in jobs if j.status == "failed"]

            runs = await run_repo.list_runs()

        return {
            "uptime_seconds": round(self.uptime_seconds, 2),
            "total_http_requests": sum(self._http_requests_total.values()),
            "total_test_runs": len(runs),
            "workers_total": len(workers),
            "workers_online": len(online_workers),
            "workers_busy": len(busy_workers),
            "jobs_queued": len(queued_jobs),
            "jobs_running": len(running_jobs),
            "jobs_completed": len(completed_jobs),
            "jobs_failed": len(failed_jobs),
        }

    async def generate_prometheus_metrics(self) -> str:
        summary = await self.get_summary_metrics()
        lines: list[str] = [
            "# HELP ai_qa_platform_uptime_seconds Total platform uptime in seconds",
            "# TYPE ai_qa_platform_uptime_seconds gauge",
            f"ai_qa_platform_uptime_seconds {summary['uptime_seconds']}",
            "",
            "# HELP ai_qa_workers_total Number of registered distributed worker runner nodes",
            "# TYPE ai_qa_workers_total gauge",
            f"ai_qa_workers_total {summary['workers_total']}",
            "",
            "# HELP ai_qa_workers_online Number of healthy online distributed worker nodes",
            "# TYPE ai_qa_workers_online gauge",
            f"ai_qa_workers_online {summary['workers_online']}",
            "",
            "# HELP ai_qa_workers_busy Number of worker nodes actively executing test jobs",
            "# TYPE ai_qa_workers_busy gauge",
            f"ai_qa_workers_busy {summary['workers_busy']}",
            "",
            "# HELP ai_qa_jobs_status Total number of distributed jobs partitioned by state",
            "# TYPE ai_qa_jobs_status gauge",
            f'ai_qa_jobs_status{{state="queued"}} {summary["jobs_queued"]}',
            f'ai_qa_jobs_status{{state="running"}} {summary["jobs_running"]}',
            f'ai_qa_jobs_status{{state="completed"}} {summary["jobs_completed"]}',
            f'ai_qa_jobs_status{{state="failed"}} {summary["jobs_failed"]}',
            "",
            "# HELP ai_qa_test_runs_total Total test suite execution runs recorded",
            "# TYPE ai_qa_test_runs_total counter",
            f"ai_qa_test_runs_total {summary['total_test_runs']}",
            "",
            "# HELP ai_qa_http_requests_total Total HTTP requests handled by the API",
            "# TYPE ai_qa_http_requests_total counter",
        ]

        if self._http_requests_total:
            for key, count in sorted(self._http_requests_total.items()):
                method, path, status = key.split(":")
                lines.append(f'ai_qa_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')
        else:
            lines.append('ai_qa_http_requests_total{method="GET",path="/api/health",status="200"} 1')

        lines.append("")
        return "\n".join(lines)


# Singleton instance
metrics_service = MetricsService()
