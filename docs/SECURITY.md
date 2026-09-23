# Security, Privacy & Secret Protection

## 1. Secret Protection Principles
1. **Never Persist Plaintext API Keys**: API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `JENKINS_API_TOKEN`) are loaded from environment variables and never written into workspace git repositories or SQLite database files.
2. **Automated Sensitive Redaction**: `SensitiveRedactor` strips:
   - Bearer / API tokens (`sk-[a-zA-Z0-9]{20,}`).
   - Password and credential query strings.
   - JWT tokens.
   - Private key blocks.
3. **Workspace Isolation & Path Traversal Guard**:
   - `WorkspaceService` verifies all requested paths resolve inside `workspace_root`.
   - Attempts to access `/etc/passwd`, `~/.ssh`, or `../` are rejected with HTTP 400.
