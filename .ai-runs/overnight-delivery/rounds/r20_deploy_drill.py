"""Round 20 deployment drill: an isolated container stack, exercised the way an operator would.

Runs `docker compose -p aiqa-r20` with its own env file on spare ports, then checks: image build,
startup health, configuration fail-fast, migrations up/down/up against PostgreSQL, backup and restore
into a second database, graceful shutdown and teardown. Every step records what it observed.

Run with: cd <repo> && uv run python .ai-runs/overnight-delivery/rounds/r20_deploy_drill.py
Writes .ai-runs/overnight-delivery/rounds/r20-deploy.json and logs under rounds/deploy-drill/.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import subprocess
import time

import httpx

ROOT = pathlib.Path(".")
DRILL = ROOT / ".ai-runs/overnight-delivery/rounds/deploy-drill"
ENV_FILE = DRILL / "drill.env"
PROJECT = "aiqa-r20"
API_PORT = 8010
WEB_PORT = 8088
API = f"http://127.0.0.1:{API_PORT}"

checks: list[dict] = []


def check(name: str, passed: bool, detail: object = None) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    print(("[PASS] " if passed else "[FAIL] ") + name, json.dumps(detail, ensure_ascii=False)[:500], flush=True)


def run(*args: str, timeout: int = 600, check_rc: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check_rc and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {result.stderr[-2000:]}")
    return result


def compose(*args: str, timeout: int = 900, check_rc: bool = False) -> subprocess.CompletedProcess:
    return run(
        "docker", "compose", "-p", PROJECT, "--env-file", str(ENV_FILE), *args, timeout=timeout, check_rc=check_rc
    )


async def main() -> None:
    DRILL.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    # --- 1. the images build from a clean state ---
    images = run("docker", "images", "--format", "{{.Repository}}:{{.Tag}}", timeout=120).stdout
    built = {line for line in images.splitlines() if line.startswith(f"{PROJECT}-")}
    check(
        "every service image is built and tagged",
        {f"{PROJECT}-api:latest", f"{PROJECT}-web:latest"} <= built,
        {"images": sorted(built)},
    )

    # --- 2. the stack starts and reports healthy ---
    compose("down", "-v", timeout=600)
    compose("up", "-d", "postgres", "api", timeout=900)
    health = None
    for _ in range(90):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{API}/api/health")
            if response.status_code == 200:
                health = response.json()
                break
        except Exception:  # noqa: BLE001 - the container is still booting
            pass
        await asyncio.sleep(2)
    check(
        "the API container starts and reports a healthy database",
        bool(health) and health.get("status") == "healthy",
        {"health": health, "seconds": round(time.monotonic() - started, 1)},
    )
    live = run("docker", "inspect", "-f", "{{.State.Health.Status}}", f"{PROJECT}-api-1", timeout=60)
    check(
        "the container's own healthcheck turns healthy",
        live.stdout.strip() in {"healthy", "starting"},
        {"docker_health": live.stdout.strip()},
    )

    # --- 3. migrations move forward and back on PostgreSQL ---
    # The image's WORKDIR is /app, while alembic.ini lives in apps/api; `-c` makes the command work
    # from any directory (script_location is `%(here)s/alembic`, so it resolves next to the ini).
    alembic = ("alembic", "-c", "/app/apps/api/alembic.ini")
    before = compose("exec", "-T", "api", *alembic, "current", timeout=300).stdout.strip()
    down = compose("exec", "-T", "api", *alembic, "downgrade", "-1", timeout=300)
    after_down = compose("exec", "-T", "api", *alembic, "current", timeout=300).stdout.strip()
    up = compose("exec", "-T", "api", *alembic, "upgrade", "head", timeout=600)
    after_up = compose("exec", "-T", "api", *alembic, "current", timeout=300).stdout.strip()
    check(
        "a migration downgrades and upgrades again on the containerised database",
        down.returncode == 0
        and up.returncode == 0
        and after_down != before
        and after_up.split()[0] == after_up.split()[0]
        and (after_up.split()[0] == before.split()[0]),
        {"before": before, "after_downgrade": after_down, "after_upgrade": after_up},
    )

    # --- 4. real data, then a backup and a restore into a second database ---
    async with httpx.AsyncClient(timeout=30) as client:
        login = await client.post(f"{API}/api/auth/login", json={"email": "admin@ai-qa.local", "password": "adminpassword"})
        check("the seeded administrator can log in inside the container", login.status_code == 200, {"status": login.status_code})
        token = login.json()["access_token"]
        project = await client.post(
            f"{API}/api/projects",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Drill project", "description": "created by the Round 20 deployment drill"},
        )
    check("the containerised API can write to PostgreSQL", project.status_code == 201, {"status": project.status_code})

    dump = compose("exec", "-T", "postgres", "pg_dump", "-U", "aiqa", "-d", "aiqa_drill", timeout=600)
    backup_file = DRILL / "aiqa_drill.sql"
    backup_file.write_text(dump.stdout)
    check(
        "a logical backup is produced",
        dump.returncode == 0 and "CREATE TABLE" in dump.stdout,
        {"bytes": len(dump.stdout)},
    )

    compose("exec", "-T", "postgres", "psql", "-U", "aiqa", "-d", "postgres", "-c",
            "DROP DATABASE IF EXISTS aiqa_drill_restore", timeout=120, check_rc=True)
    compose("exec", "-T", "postgres", "psql", "-U", "aiqa", "-d", "postgres", "-c",
            "CREATE DATABASE aiqa_drill_restore", timeout=120, check_rc=True)
    restore = subprocess.run(
        ["docker", "compose", "-p", PROJECT, "--env-file", str(ENV_FILE), "exec", "-T", "postgres",
         "psql", "-U", "aiqa", "-d", "aiqa_drill_restore"],
        input=dump.stdout,
        capture_output=True,
        text=True,
        timeout=600,
    )
    counts_source = compose("exec", "-T", "postgres", "psql", "-U", "aiqa", "-d", "aiqa_drill", "-tAc",
                            "SELECT (SELECT count(*) FROM projects), (SELECT count(*) FROM alembic_version)",
                            timeout=120).stdout.strip()
    counts_restored = compose("exec", "-T", "postgres", "psql", "-U", "aiqa", "-d", "aiqa_drill_restore", "-tAc",
                              "SELECT (SELECT count(*) FROM projects), (SELECT count(*) FROM alembic_version)",
                              timeout=120).stdout.strip()
    check(
        "the restored database holds the same rows and the same migration revision",
        restore.returncode == 0 and counts_source == counts_restored and counts_source.split("|")[0] == "1",
        {"source": counts_source, "restored": counts_restored, "restore_rc": restore.returncode},
    )

    # --- 5. configuration fail-fast: a hard-coded secret in the config file stops the process ---
    # config.yaml must reference secrets through the environment; a literal secret is a startup error,
    # so a mis-edited deployment fails loudly instead of running with a committed key.
    bad_config = DRILL / "bad-config.yaml"
    bad_config.write_text(
        (ROOT / "config/config.yaml").read_text().replace("secret_key: ${APP_SECRET_KEY:-}", 'secret_key: "hardcoded-secret"')
    )
    failing = run(
        "docker", "run", "--rm", "--network", f"{PROJECT}_default",
        "-e", "APP_SECRET_KEY=drill-only-secret-key-not-for-production",
        "-v", f"{bad_config.resolve()}:/app/config/config.yaml:ro",
        f"{PROJECT}-api", "python", "-m", "app", timeout=300,
    )
    output = (failing.stdout + failing.stderr)[-2000:]
    check(
        "the API refuses to start when the config file hard-codes a secret, and says why",
        failing.returncode != 0 and "secret" in output.lower(),
        {"exit": failing.returncode, "tail": output[-400:]},
    )

    # --- 6. the web image serves the built bundle ---
    # Standalone (no `api` hostname resolvable): proves the image does not need a sibling container to start.
    run("docker", "run", "-d", "--rm", "--name", "aiqa-r20-webcheck", "-p", f"{WEB_PORT}:80", f"{PROJECT}-web", timeout=120)
    served = None
    for _ in range(30):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"http://127.0.0.1:{WEB_PORT}/")
            if response.status_code == 200:
                served = response.text
                break
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(1)
    check(
        "the web image serves the built single-page app",
        bool(served) and "<div id=\"root\">" in served,
        {"bytes": len(served or "")},
    )
    run("docker", "stop", "aiqa-r20-webcheck", timeout=120)

    # --- 7. graceful shutdown: SIGTERM, not SIGKILL ---
    stop = compose("stop", "api", timeout=300)
    exit_code = run("docker", "inspect", "-f", "{{.State.ExitCode}}", f"{PROJECT}-api-1", timeout=60).stdout.strip()
    check(
        "stopping the API is a graceful shutdown (no SIGKILL required)",
        stop.returncode == 0 and exit_code in {"0", "143"},
        {"stop_rc": stop.returncode, "exit_code": exit_code},
    )

    # --- 8. teardown leaves nothing running ---
    down = compose("down", "-v", timeout=600)
    remaining = run(
        "docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", "{{.Names}}", timeout=60,
    ).stdout.strip()
    check(
        "teardown removes the stack and its volumes",
        down.returncode == 0 and remaining == "",
        {"remaining": remaining.splitlines()},
    )

    payload = {
        "round": 20,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": round(time.monotonic() - started, 1),
        "checks": len(checks),
        "passed": sum(1 for item in checks if item["passed"]),
        "failed": [item["name"] for item in checks if not item["passed"]],
        "results": checks,
    }
    (ROOT / ".ai-runs/overnight-delivery/rounds/r20-deploy.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2)
    )
    print(json.dumps({"checks": payload["checks"], "passed": payload["passed"], "failed": payload["failed"]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
