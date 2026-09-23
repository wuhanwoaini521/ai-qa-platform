# Workspace Model & Storage Philosophy

## Core Principles

1. **Source Code Belongs to Git**:
   Test code, Page Object Models, custom flows, and domain knowledge definitions reside in standard Git repositories within the workspace filesystem.

2. **Platform Database Stores Metadata**:
   Projects, Requirements, Test Designs, Test Cases, Execution metadata, and Failure Diagnoses are stored in the platform database (SQLite for local dev / PostgreSQL for production).

3. **Workspace is an Editable Checkout**:
   Each project has a dedicated working directory under `runtime/workspaces/{project_id}` initialized with standard QA scaffold folders:
   - `tests/`
   - `pages/`
   - `flows/`
   - `components/`
   - `knowledge/`

4. **Runtime Artifacts are Not Source Code**:
   Screenshots, trace zip files, video recordings, and DOM dumps generated during test runs are managed independently through `ArtifactStorageService` under `runtime/artifacts/` with cloud storage pluggability (S3/MinIO) planned for future phases.

---

## Directory Confinement & Path Safety

All workspace service calls are validated using strict path resolution:
```python
def _resolve_safe_file_path(self, workspace_id: str, relative_path: str) -> Path:
    ws_dir = self.get_workspace_dir(workspace_id)
    cleaned = relative_path.lstrip("/\\")
    target = (ws_dir / cleaned).resolve()
    if not (str(target) == str(ws_dir) or str(target).startswith(str(ws_dir) + "/")):
        raise SecurityException(f"Path traversal detected: {relative_path}")
    return target
```
Attempts to access paths outside the target workspace directory are rejected immediately.
