#!/usr/bin/env python3
"""Cross-platform task runner for the AI QA Platform.

One implementation of every developer entry point, runnable from `bash`, `zsh`, PowerShell,
`cmd.exe` and `make`. The bash scripts in this directory, the Makefile and the root `package.json`
all delegate here, so macOS and Windows execute the exact same steps in the exact same order.

Tasks: setup, dev, test, lint, build, clean.

Toolchain resolution: when `mise` is on PATH every command runs through `mise exec --`, which is
how the repository pins Python/Node/uv (`mise.toml`). Without mise the already-installed tools are
used directly, so a Windows machine that installed Python and Node globally still works.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"

#: Tools whose absence is a configuration error rather than a reason to guess.
REQUIRED_TOOLS = ("uv", "pnpm")


def log(message: str) -> None:
    print(message, flush=True)


def _force_utf8_output() -> None:
    """Make stdout/stderr tolerate the glyphs Vite and uvicorn print.

    A Chinese Windows console defaults to GBK, which cannot encode arrows, box-drawing or the
    spinner characters in a dev-server banner. Writing one raises UnicodeEncodeError and kills the
    streaming thread, after which that server's logs vanish with no error shown. Substituting the
    offending characters keeps the stream alive; the text stays ASCII-safe for the terminal.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")


def use_mise() -> bool:
    """Whether commands must run through `mise exec --` to honour mise.toml."""
    return shutil.which("mise") is not None and (ROOT / "mise.toml").is_file()


def command(tool: str, *args: str) -> list[str]:
    """Build the argv for a repository tool, routed through mise when it is available."""
    if use_mise():
        return ["mise", "exec", "--", tool, *args]
    return [tool, *args]


def run(tool: str, *args: str, capture: bool = False) -> int:
    """Run a single command to completion, streaming or capturing its output."""
    argv = command(tool, *args)
    log(f"$ {' '.join(argv)}")
    if capture:
        completed = subprocess.run(argv, cwd=ROOT, check=False)
        return completed.returncode
    # Inherit stdio so the child writes straight to this terminal: interactive prompts, progress
    # bars and colour all keep working without a pty, which Windows has no equivalent of.
    completed = subprocess.run(argv, cwd=ROOT, check=False)
    return completed.returncode


def uv(*args: str, capture: bool = False) -> int:
    return run("uv", *args, capture=capture)


def pnpm(*args: str) -> int:
    return run("pnpm", *args)


def require_tools() -> None:
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        log(f"error: required tool(s) not on PATH: {', '.join(missing)}")
        log("Install them, then run `mise install` if you use mise, and retry.")
        raise SystemExit(1)


def _terminate_tree(process: subprocess.Popen) -> None:
    """Stop a child process and everything it spawned.

    `uvicorn --reload` runs the app in a grandchild process. On POSIX a process group kill reaches
    it; on Windows `Popen.terminate` only kills the direct child, so `taskkill /T` is required or
    the reloader survives the shutdown and keeps the port bound.
    """
    if process.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()


def _stream(label: str, pipe, lock: threading.Lock) -> None:
    """Forward one process's output line by line, tagged so interleaved logs stay readable."""
    for raw in iter(pipe.readline, ""):
        with lock:
            sys.stdout.write(f"[{label}] {raw}")
            sys.stdout.flush()
    pipe.close()


def _spawn(
    label: str,
    argv: list[str],
    lock: threading.Lock,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen:
    log(f"[{label}] $ {' '.join(argv)}")
    kwargs: dict = {}
    if IS_WINDOWS:
        # Detach from the console's Ctrl+C handling: this runner decides when both children stop,
        # instead of the signal racing us into a half-torn-down process tree.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(
        argv,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env={**os.environ, **(extra_env or {})},
        **kwargs,
    )
    threading.Thread(target=_stream, args=(label, process.stdout, lock), daemon=True).start()
    return process


def _available_port(preferred: int, *, attempts: int = 100) -> int:
    """Use the requested local port, or find the next free port without killing its owner."""
    if not 1 <= preferred <= 65535:
        raise ValueError(f"port must be between 1 and 65535, got {preferred}")

    for port in range(preferred, min(preferred + attempts, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"no free localhost port found from {preferred} through 65535")


def _dev_port(env_name: str, default: int) -> int:
    configured = os.getenv(env_name, "").strip()
    try:
        preferred = int(configured) if configured else default
    except ValueError as error:
        raise ValueError(f"{env_name} must be an integer port, got {configured!r}") from error

    selected = _available_port(preferred)
    if selected != preferred:
        log(f"Port {preferred} is occupied; using {selected}. Set {env_name} to choose another preferred port.")
    return selected


def task_setup() -> int:
    require_tools()
    if use_mise():
        log("Installing the mise-managed toolchain (Python 3.13, Node 24, uv)...")
        if run("mise", "install") != 0:
            return 1
    log("Syncing the Python workspace...")
    if uv("sync", "--all-packages") != 0:
        return 1
    log("Installing frontend dependencies...")
    return pnpm("install")


def task_dev() -> int:
    """Run the FastAPI backend and the Vite dev server together until interrupted."""
    require_tools()
    try:
        api_port = _dev_port("AI_QA_API_PORT", 8000)
        web_port = _dev_port("AI_QA_WEB_PORT", 5173)
    except (ValueError, RuntimeError) as error:
        log(f"error: {error}")
        return 1
    log("=" * 42)
    log("  AI QA Platform — development mode")
    log("=" * 42)
    log(f"Backend API : http://127.0.0.1:{api_port}  (docs at /docs)")
    log(f"Web app     : http://127.0.0.1:{web_port}")
    log("Press Ctrl+C to stop both.\n")

    lock = threading.Lock()
    # Uvicorn's Windows reloader selects SelectorEventLoop so it can supervise subprocesses.
    # Playwright's async driver uses asyncio subprocesses, which SelectorEventLoop does not
    # support on Windows. Run the API without hot reload there so recorder sessions and browser
    # automation use the default ProactorEventLoop. POSIX keeps the usual reload workflow.
    api_reload_args = (
        []
        if IS_WINDOWS
        else ["--reload", "--reload-dir", "apps/api", "--reload-dir", "packages"]
    )
    if IS_WINDOWS:
        log("Windows: API hot reload is disabled because Playwright requires ProactorEventLoop.")
    services = [
        (
            "api",
            command(
                "uv", "run", "uvicorn", "app.main:app", "--app-dir", "apps/api", *api_reload_args,
                "--host", "127.0.0.1", "--port", str(api_port),
            ),
            {},
        ),
        (
            "web",
            command(
                "pnpm", "--filter", "@ai-qa/web", "dev",
                "--host", "127.0.0.1", "--port", str(web_port), "--strictPort",
            ),
            {"VITE_DEV_API_TARGET": f"http://127.0.0.1:{api_port}"},
        ),
    ]
    running = [(label, _spawn(label, argv, lock, extra_env)) for label, argv, extra_env in services]
    processes = [process for _, process in running]

    def shutdown(*_: object) -> None:
        for process in processes:
            _terminate_tree(process)

    signal.signal(signal.SIGINT, shutdown)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, shutdown)

    # Whichever server exits first takes the whole session down: a dev loop where the API died
    # silently and only the UI kept running hides the real failure.
    try:
        while True:
            failed = [pair for pair in running if pair[1].poll() is not None]
            if failed:
                log(f"\nerror: the {failed[0][0]} service exited unexpectedly; stopping the session.")
                shutdown()
                return failed[0][1].returncode or 1
            threading.Event().wait(0.5)
    finally:
        shutdown()


def task_test() -> int:
    require_tools()
    log("Running Python backend tests (SQLite)...")
    if uv("run", "pytest") != 0:
        return 1

    if os.getenv("AI_QA_TEST_DATABASE_URL"):
        log("AI_QA_TEST_DATABASE_URL is set: rerunning the suite on PostgreSQL...")
        if uv("run", "pytest") != 0:
            return 1
    else:
        log("Skipping the PostgreSQL lane: set AI_QA_TEST_DATABASE_URL to a PostgreSQL URL to run it.")
        log("  e.g. AI_QA_TEST_DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/postgres'")

    log("Running frontend typecheck, lint & build...")
    for step in (("typecheck",), ("lint",), ("build",)):
        if pnpm("--filter", "@ai-qa/web", *step) != 0:
            return 1

    log("All tests passed successfully!")
    return 0


def task_lint() -> int:
    require_tools()
    log("Linting Python code with ruff...")
    if uv("run", "ruff", "check", ".") != 0:
        return 1

    log("Checking Python formatting...")
    if uv("run", "ruff", "format", "--check", ".") != 0:
        return 1

    log("Checking translation parity...")
    # `sys.executable` rather than a hardcoded `python3`, which does not exist on a stock Windows
    # install where Python registers itself as `python.exe`.
    if uv("run", "python", "scripts/i18n_check.py") != 0:
        return 1

    log("Linting frontend...")
    if pnpm("--filter", "@ai-qa/web", "lint") != 0:
        return 1

    log("All linters passed!")
    return 0


def task_build() -> int:
    require_tools()
    return pnpm("--filter", "@ai-qa/web", "build")


def task_clean() -> int:
    """Remove generated build output and local state. Replaces `rm -rf` from the Makefile."""
    targets = [
        ROOT / ".venv",
        ROOT / "node_modules",
        ROOT / "apps" / "web" / "node_modules",
        ROOT / "apps" / "web" / "dist",
    ]
    for target in targets:
        if target.exists():
            log(f"Removing {target.relative_to(ROOT)}")
            shutil.rmtree(target, ignore_errors=True)

    database = ROOT / "runtime" / "ai_qa_platform.db"
    if database.exists():
        log(f"Removing {database.relative_to(ROOT)}")
        database.unlink()


TASKS = {
    "setup": task_setup,
    "dev": task_dev,
    "test": task_test,
    "lint": task_lint,
    "build": task_build,
    "clean": task_clean,
}


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=sorted(TASKS), help="task to run")
    args = parser.parse_args(argv)
    return TASKS[args.task]()


if __name__ == "__main__":
    sys.exit(main())
