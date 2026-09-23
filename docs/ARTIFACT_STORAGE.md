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
