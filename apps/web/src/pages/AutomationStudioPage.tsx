import React, { useEffect, useState, useCallback, useRef } from 'react';
import Editor, { OnMount } from '@monaco-editor/react';
import {
  Project,
  FileNode,
  GitDiffResult,
  ValidationIssue,
  CollectedTest,
  QAChatResponse,
} from '../types';
import { api } from '../api/client';
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  Save,
  GitBranch,
  RefreshCw,
  Play,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Bot,
  Plus,
  Trash2,
  Edit2,
  Search,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  X,
  FilePlus,
  FolderPlus,
  Send,
  Terminal,
  Check,
} from 'lucide-react';

interface TabItem {
  path: string;
  name: string;
  content: string;
  initialContent: string;
  isDirty: boolean;
}

interface AutomationStudioPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onSelectProject: (id: string) => void;
  onNavigateToRuns?: (runId?: string) => void;
  initialOpenFilePath?: string | null;
}

export const AutomationStudioPage: React.FC<AutomationStudioPageProps> = ({
  projects,
  selectedProjectId,
  onSelectProject,
  onNavigateToRuns,
  initialOpenFilePath,
}) => {
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  // File Tree & Multi-Tab State
  const [files, setFiles] = useState<FileNode[]>([]);
  const [allFilePaths, setAllFilePaths] = useState<string[]>([]);
  const [tabs, setTabs] = useState<TabItem[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  const [loadingFile, setLoadingFile] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  // Sidebar Mode: 'files' | 'tests'
  const [sidebarTab, setSidebarTab] = useState<'files' | 'tests'>('files');
  const [collectedTests, setCollectedTests] = useState<CollectedTest[]>([]);
  const [loadingTests, setLoadingTests] = useState<boolean>(false);

  // Quick Open Modal (Cmd+P)
  const [showQuickOpen, setShowQuickOpen] = useState<boolean>(false);
  const [quickOpenQuery, setQuickOpenQuery] = useState<string>('');
  const [quickOpenSelectedIndex, setQuickOpenSelectedIndex] = useState<number>(0);

  // File Operations Modals
  const [fileOpModal, setFileOpModal] = useState<{
    type: 'create_file' | 'create_folder' | 'rename' | 'delete';
    targetPath?: string;
    newName?: string;
  } | null>(null);
  const [opInputText, setOpInputText] = useState<string>('');

  // Source Control & Commit
  const [diffResult, setDiffResult] = useState<GitDiffResult>({ diff: '', changed_files: [] });
  const [showDiffView, setShowDiffView] = useState<boolean>(false);
  const [commitMessage, setCommitMessage] = useState<string>('');
  const [isCommitting, setIsCommitting] = useState<boolean>(false);

  // Expanded folders in explorer
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({
    tests: true,
    pages: true,
    flows: true,
    knowledge: true,
  });

  // Bottom Problems Panel & Validation
  const [showProblemsPanel, setShowProblemsPanel] = useState<boolean>(false);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>([]);
  const [validating, setValidating] = useState<boolean>(false);

  // QA Assistant Sidecar State
  const [assistantMessages, setAssistantMessages] = useState<
    Array<{ role: 'user' | 'assistant'; text: string; codeSnippet?: string | null; actions?: string[] }>
  >([
    {
      role: 'assistant',
      text: 'Hello! I am your AI QA Assistant. I can help you write Playwright & Pytest tests, explain code, diagnose test failures, or suggest locator refactorings.',
      actions: ['Explain Code', 'Generate Test', 'Suggest Refactor', 'Diagnose Errors'],
    },
  ]);
  const [assistantInput, setAssistantInput] = useState<string>('');
  const [assistantLoading, setAssistantLoading] = useState<boolean>(false);

  // Execution from Studio
  const [runningTest, setRunningTest] = useState<boolean>(false);
  const [lastRunResult, setLastRunResult] = useState<string | null>(null);

  // Monaco Editor Ref
  const editorRef = useRef<any>(null);

  const activeTab = tabs.find((t) => t.path === activeTabPath);

  // Flatten file paths for quick open
  const extractPaths = (nodes: FileNode[]): string[] => {
    let result: string[] = [];
    for (const node of nodes) {
      if (node.type === 'file') {
        result.push(node.path);
      }
      if (node.children) {
        result = result.concat(extractPaths(node.children));
      }
    }
    return result;
  };

  const fetchFiles = async () => {
    if (!currentProjectId) return;
    try {
      const tree = await api.getWorkspaceFiles(currentProjectId);
      setFiles(tree);
      setAllFilePaths(extractPaths(tree));
      const diff = await api.getWorkspaceDiff(currentProjectId);
      setDiffResult(diff);
    } catch (err) {
      console.error('Failed to load workspace files', err);
    }
  };

  const fetchCollectedTests = async () => {
    if (!currentProjectId) return;
    try {
      setLoadingTests(true);
      const tests = await api.collectWorkspaceTests(currentProjectId);
      setCollectedTests(tests);
    } catch (err) {
      console.error('Failed to collect workspace tests', err);
    } finally {
      setLoadingTests(false);
    }
  };

  const handleValidateWorkspace = async () => {
    if (!currentProjectId) return;
    try {
      setValidating(true);
      const res = await api.validateWorkspace(currentProjectId);
      setValidationIssues(res.issues);
      if (res.issues.length > 0) {
        setShowProblemsPanel(true);
      }
    } catch (err) {
      console.error('Failed to validate workspace', err);
    } finally {
      setValidating(false);
    }
  };

  useEffect(() => {
    fetchFiles();
    fetchCollectedTests();
    handleValidateWorkspace();
  }, [currentProjectId]);

  useEffect(() => {
    if (initialOpenFilePath) {
      handleOpenFile(initialOpenFilePath);
    }
  }, [initialOpenFilePath]);

  // Open file in tabs
  const handleOpenFile = async (path: string) => {
    if (!currentProjectId) return;
    const existingIndex = tabs.findIndex((t) => t.path === path);
    if (existingIndex !== -1) {
      setActiveTabPath(path);
      setShowDiffView(false);
      return;
    }

    try {
      setLoadingFile(true);
      const res = await api.readWorkspaceFile(currentProjectId, path);
      const filename = path.split('/').pop() || path;
      const newTab: TabItem = {
        path,
        name: filename,
        content: res.content,
        initialContent: res.content,
        isDirty: false,
      };
      setTabs((prev) => [...prev, newTab]);
      setActiveTabPath(path);
      setShowDiffView(false);
    } catch (err) {
      console.error(`Failed to read file ${path}`, err);
    } finally {
      setLoadingFile(false);
    }
  };

  const handleCloseTab = (path: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const tabToClose = tabs.find((t) => t.path === path);
    if (tabToClose?.isDirty) {
      const confirmClose = window.confirm(
        `File '${tabToClose.name}' has unsaved changes. Do you want to close it?`
      );
      if (!confirmClose) return;
    }

    const nextTabs = tabs.filter((t) => t.path !== path);
    setTabs(nextTabs);
    if (activeTabPath === path) {
      if (nextTabs.length > 0) {
        setActiveTabPath(nextTabs[nextTabs.length - 1].path);
      } else {
        setActiveTabPath(null);
      }
    }
  };

  const handleUpdateContent = (value: string | undefined) => {
    const newContent = value ?? '';
    if (!activeTabPath) return;
    setTabs((prev) =>
      prev.map((t) => {
        if (t.path === activeTabPath) {
          return {
            ...t,
            content: newContent,
            isDirty: newContent !== t.initialContent,
          };
        }
        return t;
      })
    );
  };

  const handleSaveActiveTab = useCallback(async () => {
    if (!currentProjectId || !activeTab || saving) return;
    try {
      setSaving(true);
      await api.writeWorkspaceFile(currentProjectId, activeTab.path, activeTab.content);
      setTabs((prev) =>
        prev.map((t) =>
          t.path === activeTab.path
            ? { ...t, initialContent: t.content, isDirty: false }
            : t
        )
      );
      // Refresh diff and run quick validation
      const diff = await api.getWorkspaceDiff(currentProjectId);
      setDiffResult(diff);
      api.validateWorkspace(currentProjectId).then((res) => {
        setValidationIssues(res.issues);
      });
      // Refresh collected tests if test file was saved
      if (activeTab.path.includes('test_') || activeTab.path.endsWith('.py')) {
        api.collectWorkspaceTests(currentProjectId).then((tests) => setCollectedTests(tests));
      }
    } catch (err) {
      console.error(`Failed to save file ${activeTab.path}`, err);
    } finally {
      setSaving(false);
    }
  }, [currentProjectId, activeTab, saving]);

  const handleSaveAll = useCallback(async () => {
    if (!currentProjectId) return;
    const dirtyTabs = tabs.filter((t) => t.isDirty);
    if (dirtyTabs.length === 0) return;
    try {
      setSaving(true);
      for (const t of dirtyTabs) {
        await api.writeWorkspaceFile(currentProjectId, t.path, t.content);
      }
      setTabs((prev) =>
        prev.map((t) => ({ ...t, initialContent: t.content, isDirty: false }))
      );
      const diff = await api.getWorkspaceDiff(currentProjectId);
      setDiffResult(diff);
      const res = await api.validateWorkspace(currentProjectId);
      setValidationIssues(res.issues);
    } catch (err) {
      console.error('Failed to save all files', err);
    } finally {
      setSaving(false);
    }
  }, [currentProjectId, tabs]);

  // Keyboard Shortcuts (Cmd/Ctrl + S, Cmd/Ctrl + Shift + S, Cmd/Ctrl + P)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'p') {
        e.preventDefault();
        setShowQuickOpen((prev) => !prev);
        setQuickOpenQuery('');
        setQuickOpenSelectedIndex(0);
      } else if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === 'S' || e.key === 's')) {
        e.preventDefault();
        handleSaveAll();
      } else if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        handleSaveActiveTab();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSaveActiveTab, handleSaveAll]);

  // File Operations Execution
  const handleExecuteFileOp = async () => {
    if (!currentProjectId || !fileOpModal) return;
    const input = opInputText.trim();
    if (!input && fileOpModal.type !== 'delete') return;

    try {
      if (fileOpModal.type === 'create_file') {
        await api.createWorkspaceFile(currentProjectId, input, '# New File\n');
        await fetchFiles();
        handleOpenFile(input);
      } else if (fileOpModal.type === 'create_folder') {
        await api.createWorkspaceDirectory(currentProjectId, input);
        await fetchFiles();
      } else if (fileOpModal.type === 'rename' && fileOpModal.targetPath) {
        await api.renameWorkspaceFile(currentProjectId, fileOpModal.targetPath, input);
        await fetchFiles();
        // Update tabs
        setTabs((prev) =>
          prev.map((t) =>
            t.path === fileOpModal.targetPath
              ? { ...t, path: input, name: input.split('/').pop() || input }
              : t
          )
        );
        if (activeTabPath === fileOpModal.targetPath) {
          setActiveTabPath(input);
        }
      } else if (fileOpModal.type === 'delete' && fileOpModal.targetPath) {
        await api.deleteWorkspaceFile(currentProjectId, fileOpModal.targetPath);
        await fetchFiles();
        handleCloseTab(fileOpModal.targetPath);
      }
    } catch (err: any) {
      alert(`Error performing file operation: ${err.message || err}`);
    } finally {
      setFileOpModal(null);
      setOpInputText('');
    }
  };

  const handleCommitChanges = async () => {
    if (!currentProjectId || !commitMessage.trim() || isCommitting) return;
    try {
      setIsCommitting(true);
      await api.commitWorkspace(currentProjectId, commitMessage.trim());
      setCommitMessage('');
      const diff = await api.getWorkspaceDiff(currentProjectId);
      setDiffResult(diff);
      setShowDiffView(false);
    } catch (err: any) {
      alert(`Commit error: ${err.message || err}`);
    } finally {
      setIsCommitting(false);
    }
  };

  const handleBootstrapWorkspace = async () => {
    if (!currentProjectId) return;
    try {
      await api.bootstrapWorkspace(currentProjectId);
      await fetchFiles();
      await fetchCollectedTests();
    } catch (err) {
      console.error('Failed to bootstrap workspace', err);
    }
  };

  // Run a specific test nodeid or the active file
  const handleRunExecution = async (targetNodeid?: string) => {
    if (!currentProjectId || runningTest) return;
    try {
      setRunningTest(true);
      setLastRunResult('Dispatching execution run...');
      const target = targetNodeid
        ? [targetNodeid]
        : activeTabPath
        ? [activeTabPath]
        : undefined;

      const run = await api.createTestRun({
        project_id: currentProjectId,
        target_nodeids: target,
        triggered_by: 'Automation Studio',
      });

      setLastRunResult(`Run #${run.id.slice(0, 8)} started with status: ${run.status}`);
      if (onNavigateToRuns) {
        onNavigateToRuns(run.id);
      }
    } catch (err: any) {
      setLastRunResult(`Execution error: ${err.message || err}`);
    } finally {
      setRunningTest(false);
    }
  };

  // Jump editor to issue line
  const handleJumpToIssue = (issue: ValidationIssue) => {
    handleOpenFile(issue.file);
    setTimeout(() => {
      if (editorRef.current) {
        editorRef.current.revealLineInCenter(issue.line);
        editorRef.current.setPosition({ lineNumber: issue.line, column: issue.column || 1 });
        editorRef.current.focus();
      }
    }, 200);
  };

  // QA Assistant message handling
  const handleSendAssistantMessage = async (customPrompt?: string, actionType?: 'chat' | 'explain' | 'generate' | 'refactor' | 'diagnose') => {
    const text = customPrompt || assistantInput.trim();
    if (!text || assistantLoading) return;

    const userMsg = { role: 'user' as const, text };
    setAssistantMessages((prev) => [...prev, userMsg]);
    if (!customPrompt) setAssistantInput('');
    setAssistantLoading(true);

    try {
      const resp: QAChatResponse = await api.askQAAssistant({
        message: text,
        project_id: currentProjectId || undefined,
        current_file: activeTab?.path,
        selected_code: activeTab?.content,
        context_type: actionType || 'chat',
      });

      setAssistantMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: resp.reply || resp.response || '',
          codeSnippet: resp.code_snippet || resp.suggested_code,
          actions: resp.suggested_actions,
        },
      ]);
    } catch (err: any) {
      setAssistantMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `Error contacting QA Assistant: ${err.message || err}`,
        },
      ]);
    } finally {
      setAssistantLoading(false);
    }
  };

  const handleInsertSnippet = (snippet: string) => {
    if (!activeTab || !editorRef.current) return;
    const selection = editorRef.current.getSelection();
    if (selection) {
      editorRef.current.executeEdits('assistant', [
        {
          range: selection,
          text: snippet,
          forceMoveMarkers: true,
        },
      ]);
    } else {
      handleUpdateContent(activeTab.content + '\n' + snippet);
    }
  };

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [path]: !prev[path],
    }));
  };

  const getLanguage = (path: string | null): string => {
    if (!path) return 'plaintext';
    if (path.endsWith('.py')) return 'python';
    if (path.endsWith('.json')) return 'json';
    if (path.endsWith('.md')) return 'markdown';
    if (path.endsWith('.ts') || path.endsWith('.tsx')) return 'typescript';
    if (path.endsWith('.js') || path.endsWith('.jsx')) return 'javascript';
    if (path.endsWith('.yaml') || path.endsWith('.yml')) return 'yaml';
    return 'plaintext';
  };

  const handleEditorDidMount: OnMount = (editor) => {
    editorRef.current = editor;
  };

  // Filtered files for Quick Open
  const filteredQuickFiles = allFilePaths.filter((p) =>
    p.toLowerCase().includes(quickOpenQuery.toLowerCase())
  );

  // Render file tree recursively
  const renderFileTree = (nodes: FileNode[], depth = 0) => {
    return nodes.map((node) => {
      const isDir = node.type === 'directory';
      const isExpanded = !!expandedFolders[node.path];
      const isSelected = activeTabPath === node.path;

      if (isDir) {
        return (
          <div key={node.path}>
            <div
              className="tree-node"
              style={{ paddingLeft: `${8 + depth * 14}px`, justifyContent: 'space-between' }}
              onClick={() => toggleFolder(node.path)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                {isExpanded ? <FolderOpen size={14} color="#3b82f6" /> : <Folder size={14} color="#3b82f6" />}
                <span style={{ fontSize: '12px' }}>{node.name}</span>
              </div>
              <div className="tree-actions" onClick={(e) => e.stopPropagation()}>
                <button
                  className="icon-btn"
                  title="New File Inside"
                  onClick={() => {
                    setFileOpModal({ type: 'create_file', targetPath: node.path });
                    setOpInputText(`${node.path}/new_file.py`);
                  }}
                >
                  <Plus size={11} />
                </button>
              </div>
            </div>
            {isExpanded && node.children && <div>{renderFileTree(node.children, depth + 1)}</div>}
          </div>
        );
      }

      return (
        <div
          key={node.path}
          className={`tree-node ${isSelected ? 'active' : ''}`}
          style={{ paddingLeft: `${22 + depth * 14}px`, justifyContent: 'space-between' }}
          onClick={() => handleOpenFile(node.path)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden' }}>
            {node.name.endsWith('.py') ? (
              <FileCode size={14} color="#10b981" />
            ) : (
              <FileText size={14} color="#64748b" />
            )}
            <span style={{ fontSize: '12px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {node.name}
            </span>
          </div>
          <div className="tree-actions" onClick={(e) => e.stopPropagation()}>
            <button
              className="icon-btn"
              title="Rename"
              onClick={() => {
                setFileOpModal({ type: 'rename', targetPath: node.path });
                setOpInputText(node.path);
              }}
            >
              <Edit2 size={11} />
            </button>
            <button
              className="icon-btn"
              title="Delete"
              onClick={() => {
                setFileOpModal({ type: 'delete', targetPath: node.path });
              }}
            >
              <Trash2 size={11} color="#ef4444" />
            </button>
          </div>
        </div>
      );
    });
  };

  if (!currentProjectId || projects.length === 0) {
    return (
      <div className="card" style={{ margin: '20px' }}>
        <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Please select or create a project first to open Automation Studio.
        </div>
      </div>
    );
  }

  return (
    <div className="studio-container">
      {/* Quick Open Dialog (Cmd+P) */}
      {showQuickOpen && (
        <div className="modal-overlay" onClick={() => setShowQuickOpen(false)}>
          <div
            className="modal-dialog"
            style={{ maxWidth: '480px', marginTop: '-150px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '12px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Search size={16} color="#64748b" />
              <input
                autoFocus
                type="text"
                className="form-control"
                style={{ border: 'none', boxShadow: 'none', padding: '4px', fontSize: '14px' }}
                placeholder="Search files by name... (Esc to close)"
                value={quickOpenQuery}
                onChange={(e) => {
                  setQuickOpenQuery(e.target.value);
                  setQuickOpenSelectedIndex(0);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setShowQuickOpen(false);
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setQuickOpenSelectedIndex((prev) =>
                      Math.min(prev + 1, filteredQuickFiles.length - 1)
                    );
                  }
                  if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setQuickOpenSelectedIndex((prev) => Math.max(prev - 1, 0));
                  }
                  if (e.key === 'Enter' && filteredQuickFiles[quickOpenSelectedIndex]) {
                    handleOpenFile(filteredQuickFiles[quickOpenSelectedIndex]);
                    setShowQuickOpen(false);
                  }
                }}
              />
            </div>
            <div style={{ maxHeight: '280px', overflowY: 'auto', padding: '6px' }}>
              {filteredQuickFiles.length === 0 ? (
                <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                  No matching files found
                </div>
              ) : (
                filteredQuickFiles.map((p, idx) => (
                  <div
                    key={p}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      fontFamily: 'var(--font-mono)',
                      background: idx === quickOpenSelectedIndex ? '#eff6ff' : 'transparent',
                      color: idx === quickOpenSelectedIndex ? '#2563eb' : '#334155',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                    onClick={() => {
                      handleOpenFile(p);
                      setShowQuickOpen(false);
                    }}
                  >
                    <span>{p}</span>
                    <span style={{ fontSize: '10px', color: '#94a3b8' }}>File</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* File Operation Modal */}
      {fileOpModal && (
        <div className="modal-overlay">
          <div className="modal-dialog" style={{ maxWidth: '420px' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: '14px', fontWeight: 700 }}>
                {fileOpModal.type === 'create_file' && 'Create New File'}
                {fileOpModal.type === 'create_folder' && 'Create New Folder'}
                {fileOpModal.type === 'rename' && 'Rename File / Directory'}
                {fileOpModal.type === 'delete' && 'Confirm Delete'}
              </h3>
              <button
                type="button"
                style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                onClick={() => setFileOpModal(null)}
              >
                ✕
              </button>
            </div>
            <div className="modal-body" style={{ padding: '16px' }}>
              {fileOpModal.type === 'delete' ? (
                <p style={{ fontSize: '13px', color: '#dc2626' }}>
                  Are you sure you want to permanently delete <code>{fileOpModal.targetPath}</code>?
                </p>
              ) : (
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label">
                    {fileOpModal.type === 'create_file' && 'File path relative to workspace root:'}
                    {fileOpModal.type === 'create_folder' && 'Directory path relative to workspace root:'}
                    {fileOpModal.type === 'rename' && 'New relative path:'}
                  </label>
                  <input
                    autoFocus
                    type="text"
                    className="form-control"
                    value={opInputText}
                    onChange={(e) => setOpInputText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleExecuteFileOp();
                      if (e.key === 'Escape') setFileOpModal(null);
                    }}
                  />
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary btn-sm" onClick={() => setFileOpModal(null)}>
                Cancel
              </button>
              <button
                className={`btn btn-sm ${fileOpModal.type === 'delete' ? 'btn-danger' : 'btn-primary'}`}
                style={fileOpModal.type === 'delete' ? { background: '#dc2626', color: '#fff' } : {}}
                onClick={handleExecuteFileOp}
              >
                {fileOpModal.type === 'delete' ? 'Delete' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Left Sidebar: File Explorer & Test Explorer */}
      <div className="studio-sidebar">
        {/* Project Selector inside studio */}
        <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '6px' }}>
          <select
            className="form-control"
            style={{ fontSize: '12px', padding: '4px 6px', flex: 1 }}
            value={currentProjectId}
            onChange={(e) => onSelectProject(e.target.value)}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            className="btn btn-secondary btn-sm"
            style={{ padding: '4px 8px' }}
            title="Quick Open File (Cmd+P)"
            onClick={() => setShowQuickOpen(true)}
          >
            <Search size={13} />
          </button>
        </div>

        {/* Sidebar View Switcher: Files vs Tests */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-color)', background: '#f8fafc' }}>
          <button
            style={{
              flex: 1,
              padding: '8px',
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              background: sidebarTab === 'files' ? '#ffffff' : 'transparent',
              border: 'none',
              borderBottom: sidebarTab === 'files' ? '2px solid var(--primary)' : 'none',
              color: sidebarTab === 'files' ? 'var(--primary)' : 'var(--text-muted)',
              cursor: 'pointer',
            }}
            onClick={() => setSidebarTab('files')}
          >
            Files
          </button>
          <button
            style={{
              flex: 1,
              padding: '8px',
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              background: sidebarTab === 'tests' ? '#ffffff' : 'transparent',
              border: 'none',
              borderBottom: sidebarTab === 'tests' ? '2px solid var(--primary)' : 'none',
              color: sidebarTab === 'tests' ? 'var(--primary)' : 'var(--text-muted)',
              cursor: 'pointer',
            }}
            onClick={() => {
              setSidebarTab('tests');
              fetchCollectedTests();
            }}
          >
            Tests ({collectedTests.length})
          </button>
        </div>

        {/* Action Header */}
        <div className="studio-sidebar-header">
          <span>{sidebarTab === 'files' ? 'Workspace Files' : 'Pytest Explorer'}</span>
          <div style={{ display: 'flex', gap: '4px' }}>
            {sidebarTab === 'files' && (
              <>
                <button
                  className="icon-btn"
                  title="New File"
                  onClick={() => {
                    setFileOpModal({ type: 'create_file' });
                    setOpInputText('tests/test_example.py');
                  }}
                >
                  <FilePlus size={13} />
                </button>
                <button
                  className="icon-btn"
                  title="New Folder"
                  onClick={() => {
                    setFileOpModal({ type: 'create_folder' });
                    setOpInputText('pages');
                  }}
                >
                  <FolderPlus size={13} />
                </button>
              </>
            )}
            <button
              className="icon-btn"
              title="Refresh"
              onClick={() => {
                fetchFiles();
                fetchCollectedTests();
              }}
            >
              <RefreshCw size={13} />
            </button>
          </div>
        </div>

        {/* Content: File Tree or Test Explorer */}
        <div className="studio-file-tree">
          {sidebarTab === 'files' ? (
            files.length === 0 ? (
              <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                <p style={{ marginBottom: '10px' }}>Workspace is uninitialized.</p>
                <button className="btn btn-primary btn-sm" onClick={handleBootstrapWorkspace}>
                  Initialize Workspace
                </button>
              </div>
            ) : (
              renderFileTree(files)
            )
          ) : (
            <div style={{ padding: '4px' }}>
              {loadingTests ? (
                <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                  Collecting pytest tests...
                </div>
              ) : collectedTests.length === 0 ? (
                <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                  No tests detected in <code>tests/</code> directory.
                </div>
              ) : (
                collectedTests.map((t) => (
                  <div
                    key={t.nodeid}
                    style={{
                      padding: '6px 8px',
                      borderRadius: '4px',
                      marginBottom: '4px',
                      background: '#f8fafc',
                      border: '1px solid var(--border-color)',
                      fontSize: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div
                        style={{
                          fontWeight: 600,
                          color: '#0f172a',
                          cursor: 'pointer',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          maxWidth: '180px',
                        }}
                        onClick={() => handleOpenFile(t.path)}
                      >
                        {t.name}
                      </div>
                      <button
                        className="btn btn-primary btn-sm"
                        style={{ padding: '2px 6px', fontSize: '11px' }}
                        disabled={runningTest}
                        onClick={() => handleRunExecution(t.nodeid)}
                        title="Run this test"
                      >
                        <Play size={10} /> Run
                      </button>
                    </div>
                    <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                      {t.path}:{t.line}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Source Control & Changes */}
        <div style={{ borderTop: '1px solid var(--border-color)', background: '#f8fafc' }}>
          <div
            style={{
              padding: '8px 12px',
              fontSize: '11px',
              fontWeight: 700,
              color: 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              cursor: 'pointer',
            }}
            onClick={() => setShowDiffView(!showDiffView)}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <GitBranch size={13} /> Changes ({diffResult.changed_files.length})
            </span>
            <span style={{ fontSize: '10px', color: 'var(--primary)' }}>
              {showDiffView ? 'Hide Diff' : 'View Diff'}
            </span>
          </div>

          {diffResult.changed_files.length > 0 && (
            <div style={{ padding: '6px 10px', borderTop: '1px solid #e2e8f0' }}>
              <div style={{ maxHeight: '90px', overflowY: 'auto', marginBottom: '6px' }}>
                {diffResult.changed_files.map((cf, idx) => (
                  <div
                    key={idx}
                    style={{
                      fontSize: '11px',
                      fontFamily: 'var(--font-mono)',
                      padding: '2px 0',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      color: '#334155',
                      cursor: 'pointer',
                    }}
                    onClick={() => handleOpenFile(cf.path)}
                  >
                    <span style={{ color: cf.status === 'M' ? '#d97706' : '#16a34a', fontWeight: 700 }}>
                      {cf.status}
                    </span>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {cf.path}
                    </span>
                  </div>
                ))}
              </div>

              {/* Quick Git Commit */}
              <div style={{ display: 'flex', gap: '4px' }}>
                <input
                  type="text"
                  placeholder="Commit msg..."
                  className="form-control"
                  style={{ fontSize: '11px', padding: '3px 6px' }}
                  value={commitMessage}
                  onChange={(e) => setCommitMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleCommitChanges();
                  }}
                />
                <button
                  className="btn btn-primary btn-sm"
                  style={{ padding: '3px 8px', fontSize: '11px' }}
                  disabled={!commitMessage.trim() || isCommitting}
                  onClick={handleCommitChanges}
                >
                  {isCommitting ? '...' : 'Commit'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Center Panel: Multi-Tab Monaco Editor or Diff View */}
      <div className="studio-editor-pane">
        {/* Tab Bar */}
        <div className="studio-editor-tabs">
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', overflowX: 'auto', flex: 1 }}>
            {tabs.map((tab) => {
              const isActive = tab.path === activeTabPath && !showDiffView;
              return (
                <div
                  key={tab.path}
                  className={`studio-tab ${isActive ? 'active' : ''}`}
                  style={{
                    background: isActive ? '#ffffff' : '#f1f5f9',
                    borderBottom: isActive ? '2px solid var(--primary)' : 'none',
                    fontWeight: isActive ? 600 : 400,
                    cursor: 'pointer',
                  }}
                  onClick={() => {
                    setActiveTabPath(tab.path);
                    setShowDiffView(false);
                  }}
                >
                  <span>{tab.name}</span>
                  {tab.isDirty && <span style={{ color: '#ef4444', fontWeight: 700 }}>*</span>}
                  <button
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 0,
                      color: 'var(--text-muted)',
                      display: 'flex',
                    }}
                    onClick={(e) => handleCloseTab(tab.path, e)}
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            })}
            {tabs.length === 0 && !showDiffView && (
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>No open tabs (Press Cmd+P to open file)</span>
            )}
          </div>

          {/* Action Buttons in Editor Bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {activeTab && (
              <button
                className="btn btn-secondary btn-sm"
                disabled={!activeTab.isDirty || saving}
                onClick={handleSaveActiveTab}
                title="Save current file (Cmd+S)"
              >
                <Save size={13} /> {saving ? 'Saving...' : 'Save'}
              </button>
            )}

            <button
              className="btn btn-secondary btn-sm"
              onClick={handleValidateWorkspace}
              disabled={validating}
              title="Validate Python syntax & QA rules"
            >
              <CheckCircle2 size={13} color={validationIssues.length === 0 ? '#16a34a' : '#ef4444'} />
              {validating ? 'Checking...' : `Problems (${validationIssues.length})`}
            </button>

            {activeTab && (activeTab.path.includes('test_') || activeTab.path.endsWith('.py')) && (
              <button
                className="btn btn-primary btn-sm"
                disabled={runningTest}
                onClick={() => handleRunExecution(activeTab.path)}
                title="Execute tests in current file"
              >
                <Play size={13} /> {runningTest ? 'Running...' : 'Run Test'}
              </button>
            )}
          </div>
        </div>

        {/* Editor or Diff View Area */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          {showDiffView ? (
            <div
              style={{
                height: '100%',
                overflowY: 'auto',
                padding: '16px',
                background: '#0f172a',
                color: '#f8fafc',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
              }}
            >
              <div style={{ marginBottom: '10px', color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase' }}>
                Git Working Tree Diff
              </div>
              <pre style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                {diffResult.diff || 'No uncommitted changes detected in working tree.'}
              </pre>
            </div>
          ) : loadingFile ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
              Loading file content...
            </div>
          ) : activeTab ? (
            <Editor
              height="100%"
              language={getLanguage(activeTab.path)}
              value={activeTab.content}
              theme="light"
              onMount={handleEditorDidMount}
              options={{
                fontSize: 13,
                fontFamily: "'JetBrains Mono', Consolas, Menlo, monospace",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                lineNumbers: 'on',
                renderLineHighlight: 'all',
                automaticLayout: true,
                tabSize: 4,
              }}
              onChange={handleUpdateContent}
            />
          ) : (
            <div
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
              }}
            >
              <FileCode size={40} style={{ opacity: 0.3, marginBottom: '12px' }} />
              <div style={{ fontSize: '14px', fontWeight: 500 }}>Select a file from the explorer or press <code>Cmd+P</code></div>
              <div style={{ fontSize: '12px', marginTop: '4px' }}>
                Write Playwright test suites, Page Objects, and test fixtures.
              </div>
            </div>
          )}
        </div>

        {/* Collapsible Bottom Problems Panel */}
        <div style={{ borderTop: '1px solid var(--border-color)', background: '#ffffff' }}>
          <div
            style={{
              padding: '6px 12px',
              background: '#f8fafc',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: 600,
            }}
            onClick={() => setShowProblemsPanel(!showProblemsPanel)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Terminal size={14} color="#64748b" />
              <span>Workspace Problems & Validation</span>
              {validationIssues.length > 0 ? (
                <span className="badge badge-p0" style={{ fontSize: '10px' }}>
                  {validationIssues.length} issues
                </span>
              ) : (
                <span className="badge badge-ready" style={{ fontSize: '10px' }}>
                  0 errors
                </span>
              )}
            </div>
            <span style={{ fontSize: '11px', color: 'var(--primary)' }}>
              {showProblemsPanel ? 'Collapse' : 'Expand'}
            </span>
          </div>

          {showProblemsPanel && (
            <div style={{ height: '140px', overflowY: 'auto', padding: '8px' }}>
              {validationIssues.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#16a34a', padding: '16px', fontSize: '12px' }}>
                  ✓ All Python syntax and QA rules valid!
                </div>
              ) : (
                <table className="data-table" style={{ fontSize: '12px' }}>
                  <thead>
                    <tr>
                      <th style={{ padding: '4px 8px' }}>Severity</th>
                      <th style={{ padding: '4px 8px' }}>File</th>
                      <th style={{ padding: '4px 8px' }}>Line</th>
                      <th style={{ padding: '4px 8px' }}>Message</th>
                      <th style={{ padding: '4px 8px' }}>Rule ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {validationIssues.map((issue, idx) => (
                      <tr
                        key={idx}
                        style={{ cursor: 'pointer' }}
                        onClick={() => handleJumpToIssue(issue)}
                      >
                        <td style={{ padding: '4px 8px' }}>
                          {issue.severity === 'error' ? (
                            <span style={{ color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <AlertCircle size={12} /> Error
                            </span>
                          ) : (
                            <span style={{ color: '#d97706', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <AlertTriangle size={12} /> Warning
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '4px 8px', fontFamily: 'var(--font-mono)' }}>{issue.file}</td>
                        <td style={{ padding: '4px 8px' }}>{issue.line}:{issue.column}</td>
                        <td style={{ padding: '4px 8px' }}>{issue.message}</td>
                        <td style={{ padding: '4px 8px', color: 'var(--text-muted)' }}>{issue.rule_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Quick Execution Log notification bar */}
          {lastRunResult && (
            <div
              style={{
                padding: '6px 12px',
                background: '#eff6ff',
                borderTop: '1px solid #bfdbfe',
                fontSize: '11px',
                color: '#1d4ed8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span>{lastRunResult}</span>
              {onNavigateToRuns && (
                <button
                  className="btn btn-secondary btn-sm"
                  style={{ padding: '2px 6px', fontSize: '10px' }}
                  onClick={() => onNavigateToRuns()}
                >
                  View in Execution Platform
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right Panel: Interactive QA Assistant Sidecar */}
      <div className="studio-assistant-pane">
        <div className="studio-sidebar-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Bot size={14} color="#9333ea" /> QA Assistant
          </span>
          <span className="badge badge-ready" style={{ fontSize: '10px' }}>
            Grounding Active
          </span>
        </div>

        {/* Assistant Quick Actions */}
        <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-color)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          <button
            className="btn btn-secondary btn-sm"
            style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
            disabled={assistantLoading}
            onClick={() => handleSendAssistantMessage('Explain the currently open file and test structure.', 'explain')}
          >
            <Sparkles size={12} color="#2563eb" /> Explain Code
          </button>
          <button
            className="btn btn-secondary btn-sm"
            style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
            disabled={assistantLoading}
            onClick={() => handleSendAssistantMessage('Generate a Playwright test scaffold following project standards.', 'generate')}
          >
            <Sparkles size={12} color="#16a34a" /> Generate Test
          </button>
          <button
            className="btn btn-secondary btn-sm"
            style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
            disabled={assistantLoading}
            onClick={() => handleSendAssistantMessage('Suggest refactoring to Page Object pattern.', 'refactor')}
          >
            <Sparkles size={12} color="#d97706" /> Refactor PO
          </button>
          <button
            className="btn btn-secondary btn-sm"
            style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
            disabled={assistantLoading}
            onClick={() => handleSendAssistantMessage('Diagnose syntax and locator stability issues.', 'diagnose')}
          >
            <AlertTriangle size={12} color="#9333ea" /> Diagnose
          </button>
        </div>

        {/* Message Stream */}
        <div style={{ padding: '12px', flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {assistantMessages.map((msg, i) => (
            <div
              key={i}
              style={{
                alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '90%',
                background: msg.role === 'user' ? '#2563eb' : '#f8fafc',
                color: msg.role === 'user' ? '#ffffff' : '#1e293b',
                padding: '8px 12px',
                borderRadius: '6px',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border-color)',
                fontSize: '12px',
              }}
            >
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{msg.text}</div>
              {msg.codeSnippet && (
                <div style={{ marginTop: '8px' }}>
                  <div
                    style={{
                      background: '#0f172a',
                      color: '#f8fafc',
                      padding: '8px',
                      borderRadius: '4px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px',
                      overflowX: 'auto',
                      maxHeight: '180px',
                    }}
                  >
                    <pre>{msg.codeSnippet}</pre>
                  </div>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ marginTop: '6px', width: '100%', fontSize: '11px', justifyContent: 'center' }}
                    onClick={() => handleInsertSnippet(msg.codeSnippet!)}
                  >
                    <Check size={12} /> Insert Code into Editor
                  </button>
                </div>
              )}
            </div>
          ))}
          {assistantLoading && (
            <div style={{ alignSelf: 'flex-start', fontSize: '12px', color: 'var(--text-muted)', padding: '6px' }}>
              QA Assistant is reasoning...
            </div>
          )}
        </div>

        {/* Assistant Input Form */}
        <div style={{ padding: '10px', borderTop: '1px solid var(--border-color)', background: '#ffffff' }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendAssistantMessage();
            }}
            style={{ display: 'flex', gap: '6px' }}
          >
            <input
              type="text"
              className="form-control"
              style={{ fontSize: '12px', padding: '6px 8px' }}
              placeholder="Ask QA assistant..."
              value={assistantInput}
              onChange={(e) => setAssistantInput(e.target.value)}
              disabled={assistantLoading}
            />
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={!assistantInput.trim() || assistantLoading}
            >
              <Send size={13} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
