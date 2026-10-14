# Automation Studio V2 Guide

Automation Studio V2 is the in-browser IDE and test engineering environment within AI QA Platform. It bridges requirements, Page Object models, and live test executions with a desktop-class editing experience.

---

## 1. Capabilities & Layout

```text
+---------------------+------------------------------------------+---------------------+
| Workspace Explorer  | Tab Bar: [test_cart.py*] [login_page.py] | QA Assistant        |
| - Files / Tests tab |------------------------------------------| (Grounding Active)  |
| - New / Rename / Del| Monaco Editor with syntax highlighting   | - Explain Code      |
| - Quick Open Cmd+P  | AST syntax validation & diagnostics      | - Generate Test     |
| - Git Changes & Comm|------------------------------------------| - Refactor to PO    |
|                     | Problems Panel: 0 errors | 2 warnings    | - Diagnose Failure  |
+---------------------+------------------------------------------+---------------------+
```

### 1.1 Multi-Tab Monaco Editor
- **Multi-Tab Management**: Open, switch, and close multiple files concurrently (`tests/`, `pages/`, `flows/`, `knowledge/`).
- **Dirty Tracking & Safe Closing**: Unsaved changes are marked with an indicator `*` and prompted before tab closure.
- **Shortcuts**:
  - `Cmd+S` / `Ctrl+S`: Save active tab.
  - `Cmd+Shift+S` / `Ctrl+Shift+S`: Save all dirty tabs.
  - `Cmd+P` / `Ctrl+P`: Quick Open file fuzzy finder.

### 1.2 File Operations & Source Control
- **File & Folder Operations**: Create files, create directories, rename paths, and delete files with confirmation dialogs.
- **Git Working Tree Diff**: Inspect modified lines against git index directly inside the editor view.
- **In-Studio Git Commit**: Commit staged changes with custom commit messages and author metadata directly from the Studio sidebar.

### 1.3 AST Validation & Problems Panel
- **Real-Time Python AST Parsing**: Validates syntax, detects indentation issues, and checks QA architecture rules upon file save or on-demand.
- **Collapsible Problems Panel**: Lists all errors and warnings with file, line, and column coordinates.
- **Jump-to-Line Navigation**: Clicking any problem row instantly opens the corresponding file and jumps the Monaco cursor to that exact line.

### 1.4 Pytest Explorer & Targeted Runner
- **Pytest Collector**: Analyzes `tests/test_*.py` files and builds a live tree of test cases and functions (`test_node_id`).
- **Targeted Run Trigger**: Run individual tests or test suites directly from the explorer or the active editor tab.

### 1.5 Python Debugger & Session Lineage
- The debugger continues to run the existing debugpy DAP adapter and pytest target. Session metadata is persisted separately from the process-local adapter and is available through `GET /api/debug/sessions/{id}`. Normal shutdown records `CLOSED`; after an unclean crash, status may remain at its last saved value and the adapter process is not recoverable.
- Opening Debug from a failure links the session to that failure's exact workspace, pytest node id, run, and execution; mismatched failure targets are rejected. Standalone Studio debugging has no originating run/execution link.
- DAP debug sessions are not `TestRun` records and do not replace Runner verdicts. Use the normal pytest Runner for persisted PASS/FAIL results; pytest exit codes remain authoritative.

### 1.5 QA Assistant Sidecar
- **Grounding**: Automatically loaded with workspace Page Object definitions (`pages/`) and engineering knowledge rules (`knowledge/`).
- **Actions**:
  - `Explain Code`: Breaks down test fixtures, async actions, and assertions.
  - `Generate Test`: Emits standard Playwright/Pytest scaffolds for acceptance criteria.
  - `Refactor to PO`: Identifies hardcoded locators and suggests Page Object extractions.
  - `Diagnose`: Analyzes flaky selector patterns and timing hazards.
  - `Insert at Cursor`: Injects generated code directly into the active editor buffer.

---

## 2. Subprocess & Workspace Safety Guarantees

1. **Workspace Boundary Safeguards**: All file operations resolve strictly inside `/workspaces/<project_id>/`. Any `..` traversal or symlink escaping is rejected with HTTP 400.
2. **Subprocess Isolation**: No `shell=True` is ever invoked. Commands execute via `asyncio.create_subprocess_exec` with explicit argument vectors.
