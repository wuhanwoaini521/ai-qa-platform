"""Round 18 — prove the task lease across two API processes on one database.

Two uvicorn processes share a scratch copy of the runtime database, so nothing in the working copy is
touched. The drill answers three questions the single-process tests cannot:

1. A second replica starting up does not block a task the first replica is executing.
2. The live owner keeps its lease while it works, and the task still finishes.
3. After the owner is killed, the lease expires and a later replica recovers the task instead of
   leaving it RUNNING forever.

Run: ``uv run python .ai-runs/overnight-delivery/rounds/r18_two_instances.py``
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
RUN_DIR = REPO / ".ai-runs/overnight-delivery"
SCRATCH = Path("/tmp/aiqa_r18")
DB = SCRATCH / "aiqa.db"
EVIDENCE = RUN_DIR / "regression/r18-two-instances.json"
LOG_A = SCRATCH / "instance-a.log"
LOG_B = SCRATCH / "instance-b.log"
LOG_C = SCRATCH / "instance-c.log"
LOG_D = SCRATCH / "instance-d.log"
PORT_A, PORT_B, PORT_C, PORT_D = 8030, 8031, 8032, 8033
EMAIL, PASSWORD = "admin@ai-qa.local", "adminpassword"
PROJECT = "proj_golden_shop_v1"

results: list[dict] = []
procs: dict[str, subprocess.Popen] = {}


def check(name: str, ok: bool, detail=None) -> None:
    results.append({"check": name, "passed": bool(ok), "detail": detail})
    print(f"[check] {name}: {'PASS' if ok else 'FAIL'} {detail if detail is not None else ''}", flush=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def free_port(port: int) -> None:
    """A previous drill can leave an instance behind; a stale listener would serve another database."""
    subprocess.run(["fuser", "-k", "-n", "tcp", str(port)], capture_output=True, check=False)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        probe = subprocess.run(["ss", "-tln"], capture_output=True, text=True, check=False).stdout
        if f":{port} " not in probe:
            return
        time.sleep(0.5)
    raise RuntimeError(f"port {port} is still in use by another process")


def start(name: str, port: int, log: Path) -> subprocess.Popen:
    free_port(port)
    handle = log.open("wb")
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{DB}",
        "AI_QA_API_PORT": str(port),
        "PYTHONUNBUFFERED": "1",
    }
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            "apps/api",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    procs[name] = proc
    return proc


def stop(name: str, *, hard: bool = False) -> None:
    proc = procs.pop(name, None)
    if proc is None or proc.poll() is not None:
        return
    try:
        if hard:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=10)
    except ProcessLookupError:
        pass


async def wait_healthy(port: int, timeout: float = 180) -> bool:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get("/api/health/ready")
                if response.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
    return False


async def login(port: int) -> str:
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
        response = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        response.raise_for_status()
        return response.json()["access_token"]


async def requirement_id(port: int, token: str) -> str:
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=60) as client:
        response = await client.get(
            "/api/requirements", headers={"Authorization": f"Bearer {token}"}, params={"project_id": PROJECT}
        )
        response.raise_for_status()
        rows = response.json()
        rows = rows if isinstance(rows, list) else rows["items"]
        preferred = [row for row in rows if row["id"] == "req_9c72a1dabe30"]
        return (preferred or rows)[0]["id"]


async def create_task(port: int, token: str, goal: str, req_id: str) -> str:
    """A requirement analysis makes one real model call, so the task stays RUNNING for tens of seconds."""
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=60) as client:
        response = await client.post(
            "/api/tasks",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "type": "ANALYZE_REQUIREMENT",
                "goal": goal,
                "project_id": PROJECT,
                "inputs": {"requirement_id": req_id},
            },
        )
        response.raise_for_status()
        return response.json()["id"]


async def task_row(port: int, token: str, task_id: str) -> dict:
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
        response = await client.get(f"/api/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})
        return response.json() if response.status_code == 200 else {"status": f"HTTP {response.status_code}"}


async def wait_status(port: int, token: str, task_id: str, wanted: set[str], timeout: float = 300) -> dict:
    deadline = time.monotonic() + timeout
    row: dict = {}
    while time.monotonic() < deadline:
        row = await task_row(port, token, task_id)
        if row.get("status") in wanted:
            return row
        await asyncio.sleep(1)
    return row


def lease_of(task_id: str) -> dict:
    connection = sqlite3.connect(DB)
    try:
        row = connection.execute(
            "SELECT status, lease_owner, lease_token, lease_expires_at FROM agent_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return {}
    return {"status": row[0], "owner": row[1], "token": row[2], "expires_at": row[3]}


def seed_requirement_analyses(requirement_id: str) -> None:
    """Write two RUNNING analyses straight into the scratch database before a peer starts."""
    import sqlite3 as sqlite

    stamp = datetime.now(timezone.utc)
    fresh = {
        "history": [
            {
                "id": "analysis_live",
                "status": "RUNNING",
                "started_at": stamp.isoformat(),
                "input_hash": "drill",
            }
        ]
    }
    stale = {
        "history": [
            {
                "id": "analysis_orphan",
                "status": "RUNNING",
                "started_at": (stamp - timedelta(hours=1)).isoformat(),
                "input_hash": "drill",
            }
        ]
    }
    deadline = time.monotonic() + 30
    while True:
        try:
            connection = sqlite.connect(DB, timeout=2)
            try:
                for key, row in (("req_live", fresh), ("req_orphan", stale)):
                    connection.execute(
                        "INSERT INTO requirements (id, project_id, title, description, acceptance_criteria,"
                        " status, qa_model, created_at, updated_at) VALUES (?, ?, ?, '', '', 'DRAFT', ?, ?, ?)",
                        (
                            key,
                            PROJECT,
                            key,
                            json.dumps(row),
                            stamp.isoformat(),
                            stamp.isoformat(),
                        ),
                    )
                connection.commit()
            finally:
                connection.close()
            return
        except sqlite.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def analysis_status(requirement_id: str) -> str | None:
    import sqlite3 as sqlite

    connection = sqlite.connect(DB, timeout=5)
    try:
        row = connection.execute("SELECT qa_model FROM requirements WHERE id = ?", (requirement_id,)).fetchone()
    finally:
        connection.close()
    if not row or not row[0]:
        return None
    return json.loads(row[0])["history"][-1].get("status")


async def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for path in (DB, Path(f"{DB}-wal"), Path(f"{DB}-shm")):
        path.unlink(missing_ok=True)
    # A copy taken while the dev stack holds the file open can be inconsistent (the write-ahead log
    # is not applied). ``backup`` asks SQLite for a consistent snapshot instead.
    source = sqlite3.connect(REPO / "runtime/ai_qa_platform.db")
    target = sqlite3.connect(DB)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    print(f"scratch database: {DB} ({DB.stat().st_size} bytes)", flush=True)

    started_at = now()
    try:
        start("a", PORT_A, LOG_A)
        if not await wait_healthy(PORT_A):
            check("instance A becomes ready", False, {"log": str(LOG_A)})
            return 1
        token_a = await login(PORT_A)
        check("instance A becomes ready", True, {"port": PORT_A})

        req = await requirement_id(PORT_A, token_a)
        # Two requirement analyses in the scratch database: one a live process is still waiting on,
        # one a dead process left behind an hour ago. Startup recovery must tell them apart.
        seed_requirement_analyses(req)
        first = await create_task(PORT_A, token_a, "Round 18: a live lease must survive a peer startup", req)
        row = await wait_status(PORT_A, token_a, first, {"RUNNING", "COMPLETED", "FAILED", "BLOCKED"}, 120)
        live = lease_of(first)
        check(
            "the first instance takes a lease when it starts work",
            bool(live.get("owner")) and (live.get("token") or 0) >= 1,
            {"task_id": first, "status": row.get("status"), **live},
        )

        # A second replica starts while the first is working. Its startup recovery must not touch it.
        if os.environ.get("R18_SKIP_PEER") != "1":
            start("b", PORT_B, LOG_B)
        ready_b = await wait_healthy(PORT_B) if os.environ.get("R18_SKIP_PEER") != "1" else False
        token_b = await login(PORT_B) if ready_b else ""
        survived = await task_row(PORT_B, token_b, first) if ready_b else {}
        check(
            "a peer startup leaves the analysis it is still waiting on running",
            analysis_status("req_live") == "RUNNING",
            {"analysis": analysis_status("req_live")},
        )
        check(
            "a peer startup closes an analysis a dead process left behind",
            analysis_status("req_orphan") == "FAILED",
            {"analysis": analysis_status("req_orphan")},
        )
        check(
            "a second replica starting up does not block the running task",
            survived.get("status") in {"RUNNING", "COMPLETED", "VERIFYING"},
            {"status_after_peer_start": survived.get("status"), "lease": lease_of(first)},
        )

        finished = await wait_status(PORT_A, token_a, first, {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED"}, 360)
        check(
            "the task still reaches a terminal state under its own owner",
            finished.get("status") == "COMPLETED",
            {"task_id": first, "status": finished.get("status"), "failure_reason": finished.get("failure_reason")},
        )

        # Now kill the owner mid-task: its lease stays in the table, so the next replica must wait for
        # it to expire rather than blocking the task on sight.
        second = await create_task(PORT_A, token_a, "Round 18: a killed owner leaves a lease behind", req)
        await wait_status(PORT_A, token_a, second, {"RUNNING"}, 120)
        second_lease = lease_of(second)
        stop("a", hard=True)
        killed_at = now()

        start("c", PORT_C, LOG_C)
        ready_c = await wait_healthy(PORT_C)
        token_c = await login(PORT_C) if ready_c else ""
        right_after = await task_row(PORT_C, token_c, second) if ready_c else {}
        check(
            "a restart right after a crash leaves an unexpired lease alone",
            right_after.get("status") == "RUNNING",
            {"status": right_after.get("status"), "lease": lease_of(second), "killed_at": killed_at},
        )

        # Wait for the lease to expire, then a restart recovers the orphan.
        await asyncio.sleep(95)
        stop("c")
        start("d", PORT_D, LOG_D)
        ready_d = await wait_healthy(PORT_D)
        token_d = await login(PORT_D) if ready_d else ""
        recovered = await task_row(PORT_D, token_d, second) if ready_d else {}
        check(
            "an expired lease lets a restart recover the orphaned task",
            recovered.get("status") == "BLOCKED",
            {"status": recovered.get("status"), "lease": lease_of(second), "second_lease": second_lease},
        )
    finally:
        for name in list(procs):
            stop(name, hard=True)

    passed = sum(1 for item in results if item["passed"])
    payload = {
        "started_at": started_at,
        "finished_at": now(),
        "database": str(DB),
        "instances": [PORT_A, PORT_B, PORT_C, PORT_D],
        "checks": len(results),
        "passed": passed,
        "failed": [item["check"] for item in results if not item["passed"]],
        "results": results,
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"checks": payload["checks"], "passed": passed, "failed": payload["failed"]}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
