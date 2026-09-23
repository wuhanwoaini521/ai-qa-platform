# GitHub & PR Engineering Workflow Integration

This document outlines the architecture, Git safety invariants, adapter specifications, and GitHub Actions PR check integration implemented in **Phase 8**.

---

## 1. Architectural Overview

The AI QA Platform integrates the local Automation Studio directly with GitHub Pull Request workflows. This bridges test authoring, validation, committing, pushing, and PR review without leaving the QA Studio.

```text
  Automation Studio
         │
         ├── Branch Management (qa/<task-id>-<slug>)
         ├── Safe Git Repository (no --force, no reset --hard)
         ├── Commit with AI-assisted messages
         ├── Push to Remote origin
         ▼
  PullRequestAdapter
   ├── FakePullRequestAdapter (for CI, test isolation, and offline dev)
   └── GitHubPullRequestAdapter (GitHub REST API via Environment Tokens)
         │
         ├── Create Pull Request with Rich QA Context
         │    ├── Linked Requirements
         │    ├── Linked Test Cases
         │    ├── Code Diff & Changed Files
         │    └── Validation / Execution Evidence
         │
         ├── GitHub Actions Status / Check Runs
         │    ├── Python Lint & Typecheck
         │    ├── Frontend Lint & Build
         │    ├── Backend Unit Tests
         │    └── E2E Integration Tests
         │
         └── CI Failure Intelligence
              └── Failure Classification & AI Diagnosis
```

---

## 2. Git Safety Invariants

To protect developer repositories and shared branches:
- **No Force Push**: `git push --force` or `--force-with-lease` is strictly prohibited.
- **No Destructive Reset**: `git reset --hard` and `git clean -fd` are disallowed.
- **Branch Naming Validation**: Branch names must conform to `^[a-zA-Z0-9_\-\.\/]+$` and cannot contain path traversal sequences (`..`) or invalid ref formats.
- **Feature Branch Convention**: Automated tests are authored on branches following `qa/<task-id>-<slug>`. Direct pushing to `main` is discouraged.

---

## 3. PullRequestAdapter Interface

```python
class PullRequestAdapter(Protocol):
    async def create_pull_request(
        self, repo_slug: str, head_branch: str, base_branch: str, title: str, body: str
    ) -> PullRequestInfo: ...

    async def get_pull_request(self, repo_slug: str, pr_number: int) -> PullRequestInfo: ...

    async def get_pr_checks(self, repo_slug: str, pr_number: int, head_branch: str = "main") -> PRChecksSummary: ...

    async def get_check_logs(self, repo_slug: str, check_run_id: str) -> str: ...

    async def diagnose_failure(self, failure_logs: str) -> PRDiagnosisResponse: ...
```

---

## 4. GitHub Actions CI Check Synchronization

- The platform queries check runs associated with the PR head commit SHA.
- Check statuses (`QUEUED`, `RUNNING`, `PASSED`, `FAILED`) are rendered live in the Automation Studio PR tab.
- When a check fails, the user can trigger **AI Failure Diagnosis** to analyze failure logs, pinpoint the root cause (Syntax, Lint, Type, Dependency, or Assertion Failure), and review suggested remedies.

---

## 5. Security & Credentials

- GitHub authentication tokens (`GITHUB_TOKEN`) are accessed strictly on the backend via environment variables or secret references.
- Raw access tokens are never sent to the web frontend client.
- When no credentials are provided, the platform gracefully switches to `FakePullRequestAdapter` for local and mock execution.
