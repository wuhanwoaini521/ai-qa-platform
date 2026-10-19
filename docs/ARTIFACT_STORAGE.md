# Artifact Storage & Retrieval

## 1. Storage

The platform stores test artifacts on the local filesystem:
- **Local Storage (`LOCAL`)**: files written under the API's artifact directory, served through
  `GET /api/artifacts/{artifact_id}/download`, with the metadata row kept in `stored_artifacts`.

> **Not implemented yet:** the `S3` storage type is reserved in the schema (`stored_artifacts.storage_type`)
> and the deployment stack provisions a MinIO service, but there is **no S3/MinIO client in the codebase** —
> all artifacts currently go to the local filesystem regardless of the `S3_*` environment variables.
> Object storage with presigned URLs is a v1.1 roadmap item. Do not configure an S3 endpoint expecting it to
> be used.

---

## 2. Supported Artifact Types

- **Playwright Traces (`.zip`)**: Downloadable for Playwright Trace Viewer inspection.
- **DOM Snapshots (`.html`, `.json`)**: Tree snapshots for AI locator repair analysis.
- **Error Screenshots (`.png`)**: Visual defect evidence.
- **Allure & HTML Reports**: Comprehensive interactive test reports.

---

## 3. Access Control

Artifacts carry the project they belong to (`stored_artifacts.project_id`) and the account that stored them
(`created_by`). Reading metadata or downloading requires the caller to be able to access that project; rows
with no project (historical data, manual uploads without a project) are readable by administrators only.
`POST /api/artifacts/upload` accepts an optional `project_id` and requires access to it. Writes performed by
the platform itself record the owning project and actor: a test run's artifacts use the run's project and
requester, exploration evidence uses the discovery run's project and requester, and task artifacts use the
task's project and owner.
