"""Run disposable UI acceptance against a temporary DB/workspace/artifact root."""
from __future__ import annotations

import tempfile
from pathlib import Path

from app.settings import config_manager, get_config

temporary_root = tempfile.TemporaryDirectory(prefix="aiqa-night-final-acceptance-")
root = Path(temporary_root.name)
base = get_config()
runtime = root / "runtime"
workspaces = root / "workspaces"
artifacts = root / "artifacts"
config_manager.replace_for_test(
    base.model_copy(
        update={
            "app": base.app.model_copy(
                update={
                    "runtime_dir": runtime,
                    "workspace_storage_dir": workspaces,
                    "artifact_storage_dir": artifacts,
                }
            ),
            "database": base.database.model_copy(update={"url": f"sqlite+aiosqlite:///{root / 'qa.db'}"}),
            "worker": base.worker.model_copy(
                update={"workspace_storage_dir": workspaces, "artifact_storage_dir": artifacts}
            ),
            # No repair analysis is started in this run; configured real providers remain active.
            "repair": base.repair.model_copy(update={"mode": "OFF", "auto_start_on_failure": False}),
        }
    )
)

from app.main import app  # noqa: E402
import uvicorn  # noqa: E402

print(f"DISPOSABLE_ACCEPTANCE_ROOT={root}", flush=True)
try:
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="warning", access_log=False)
finally:
    temporary_root.cleanup()
