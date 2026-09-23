# Multi-Backend Artifact Storage & Retrieval

## 1. Storage Abstraction

The platform supports pluggable storage backends:
- **Local Storage (`LOCAL`)**: Direct file storage with path confinement and secure read permissions.
- **S3 / MinIO Object Storage (`S3`)**: Cloud object store with bucket partitioning, presigned download URLs, and lifecycle expiry policies.

---

## 2. Supported Artifact Types

- **Playwright Traces (`.zip`)**: Downloadable for Playwright Trace Viewer inspection.
- **DOM Snapshots (`.html`, `.json`)**: Tree snapshots for AI locator repair and healing.
- **Error Screenshots (`.png`)**: Visual defect evidence.
- **Allure & HTML Reports**: Comprehensive interactive test reports.
