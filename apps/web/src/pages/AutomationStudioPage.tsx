import React, { useEffect, useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { Project, FileNode, GitDiffResult } from '../types';
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
} from 'lucide-react';

interface AutomationStudioPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onSelectProject: (id: string) => void;
}

export const AutomationStudioPage: React.FC<AutomationStudioPageProps> = ({
  projects,
  selectedProjectId,
  onSelectProject,
}) => {
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  const [files, setFiles] = useState<FileNode[]>([]);
  const [openFilePath, setOpenFilePath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [initialContent, setInitialContent] = useState<string>('');
  const [isDirty, setIsDirty] = useState<boolean>(false);
  const [loadingFile, setLoadingFile] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  // Source control
  const [diffResult, setDiffResult] = useState<GitDiffResult>({ diff: '', changed_files: [] });
  const [showDiffView, setShowDiffView] = useState<boolean>(false);
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({
    tests: true,
    pages: true,
    flows: true,
  });

  const fetchFiles = async () => {
    if (!currentProjectId) return;
    try {
      const tree = await api.getWorkspaceFiles(currentProjectId);
      setFiles(tree);
      const diff = await api.getWorkspaceDiff(currentProjectId);
      setDiffResult(diff);
    } catch (err) {
      console.error('Failed to load workspace files', err);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, [currentProjectId]);

  const handleOpenFile = async (path: string) => {
    if (!currentProjectId) return;
    try {
      setLoadingFile(true);
      const res = await api.readWorkspaceFile(currentProjectId, path);
      setOpenFilePath(path);
      setFileContent(res.content);
      setInitialContent(res.content);
      setIsDirty(false);
      setShowDiffView(false);
    } catch (err) {
      console.error(`Failed to read file ${path}`, err);
    } finally {
      setLoadingFile(false);
    }
  };

  const handleSaveFile = useCallback(async () => {
    if (!currentProjectId || !openFilePath || saving) return;
    try {
      setSaving(true);
      await api.writeWorkspaceFile(currentProjectId, openFilePath, fileContent);
      setInitialContent(fileContent);
      setIsDirty(false);
      // Refresh git status
      const diff = await api.getWorkspaceDiff(currentProjectId);
      setDiffResult(diff);
    } catch (err) {
      console.error(`Failed to save file ${openFilePath}`, err);
    } finally {
      setSaving(false);
    }
  }, [currentProjectId, openFilePath, fileContent, saving]);

  // Keyboard shortcut Cmd/Ctrl + S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        handleSaveFile();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSaveFile]);

  const handleBootstrapWorkspace = async () => {
    if (!currentProjectId) return;
    try {
      await api.bootstrapWorkspace(currentProjectId);
      await fetchFiles();
    } catch (err) {
      console.error('Failed to bootstrap workspace', err);
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

  // Render file tree recursively
  const renderFileTree = (nodes: FileNode[], depth = 0) => {
    return nodes.map((node) => {
      const isDir = node.type === 'directory';
      const isExpanded = !!expandedFolders[node.path];
      const isSelected = openFilePath === node.path;

      if (isDir) {
        return (
          <div key={node.path}>
            <div
              className="tree-node"
              style={{ paddingLeft: `${8 + depth * 14}px` }}
              onClick={() => toggleFolder(node.path)}
            >
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              {isExpanded ? <FolderOpen size={14} color="#3b82f6" /> : <Folder size={14} color="#3b82f6" />}
              <span>{node.name}</span>
            </div>
            {isExpanded && node.children && (
              <div>{renderFileTree(node.children, depth + 1)}</div>
            )}
          </div>
        );
      }

      return (
        <div
          key={node.path}
          className={`tree-node ${isSelected ? 'active' : ''}`}
          style={{ paddingLeft: `${22 + depth * 14}px` }}
          onClick={() => handleOpenFile(node.path)}
        >
          {node.name.endsWith('.py') ? (
            <FileCode size={14} color="#10b981" />
          ) : (
            <FileText size={14} color="#64748b" />
          )}
          <span>{node.name}</span>
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
      {/* Left Panel: File Tree & Git Status */}
      <div className="studio-sidebar">
        <div className="studio-sidebar-header">
          <span>Workspace Explorer</span>
          <button
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
            onClick={fetchFiles}
            title="Refresh files"
          >
            <RefreshCw size={13} />
          </button>
        </div>

        {/* Project Selector inside studio */}
        <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-color)' }}>
          <select
            className="form-control"
            style={{ fontSize: '12px', padding: '4px 6px' }}
            value={currentProjectId}
            onChange={(e) => onSelectProject(e.target.value)}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* Files */}
        <div className="studio-file-tree">
          {files.length === 0 ? (
            <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
              <p style={{ marginBottom: '10px' }}>Workspace is uninitialized.</p>
              <button className="btn btn-primary btn-sm" onClick={handleBootstrapWorkspace}>
                Initialize Workspace
              </button>
            </div>
          ) : (
            renderFileTree(files)
          )}
        </div>

        {/* Source Control Summary */}
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
            <div style={{ maxHeight: '120px', overflowY: 'auto', padding: '4px 8px' }}>
              {diffResult.changed_files.map((cf, idx) => (
                <div
                  key={idx}
                  style={{
                    fontSize: '11px',
                    fontFamily: 'var(--font-mono)',
                    padding: '2px 4px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    color: '#334155',
                    cursor: 'pointer',
                  }}
                  onClick={() => handleOpenFile(cf.path)}
                >
                  <span
                    style={{
                      color: cf.status === 'M' ? '#d97706' : '#16a34a',
                      fontWeight: 700,
                    }}
                  >
                    {cf.status}
                  </span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {cf.path}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Center Panel: Editor or Diff View */}
      <div className="studio-editor-pane">
        <div className="studio-editor-tabs">
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {openFilePath ? (
              <div className="studio-tab">
                <span>{openFilePath}</span>
                {isDirty && <span style={{ color: '#ef4444', fontWeight: 700 }}>*</span>}
              </div>
            ) : (
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>No file open</span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {openFilePath && (
              <button
                className="btn btn-primary btn-sm"
                disabled={!isDirty || saving}
                onClick={handleSaveFile}
              >
                <Save size={13} /> {saving ? 'Saving...' : 'Save (Cmd+S)'}
              </button>
            )}
          </div>
        </div>

        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          {showDiffView ? (
            <div style={{ height: '100%', overflowY: 'auto', padding: '16px', background: '#0f172a', color: '#f8fafc', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
              <div style={{ marginBottom: '10px', color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Git Working Tree Diff
              </div>
              <pre style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                {diffResult.diff || 'No uncommitted changes detected in working tree.'}
              </pre>
            </div>
          ) : loadingFile ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
              Loading file...
            </div>
          ) : openFilePath ? (
            <Editor
              height="100%"
              language={getLanguage(openFilePath)}
              value={fileContent}
              theme="light"
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
              onChange={(value) => {
                const updated = value ?? '';
                setFileContent(updated);
                setIsDirty(updated !== initialContent);
              }}
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
              <div style={{ fontSize: '14px', fontWeight: 500 }}>Select a file from the explorer to view and edit</div>
              <div style={{ fontSize: '12px', marginTop: '4px' }}>
                Automated tests, Page Objects, Flows, and Knowledge rules
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Panel: QA Assistant Placeholder */}
      <div className="studio-assistant-pane">
        <div className="studio-sidebar-header">
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Bot size={14} color="#9333ea" /> QA Assistant
          </span>
          <span className="sidebar-brand-badge">Coming Soon</span>
        </div>

        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px', flex: 1, overflowY: 'auto' }}>
          <div style={{ background: '#f8fafc', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
              <Sparkles size={14} color="#2563eb" /> AI Test Author
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Generate complete Playwright and Pytest automation code from requirement acceptance criteria.
            </p>
          </div>

          <div style={{ background: '#f8fafc', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
              <Sparkles size={14} color="#16a34a" /> Locator Healing
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Automatically diagnose broken selectors from test traces and apply DOM healing suggestions.
            </p>
          </div>

          <div style={{ background: '#f8fafc', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '4px' }}>
              <Play size={14} color="#d97706" /> Interactive Studio Runner
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Targeted in-browser test execution with live failure streaming and DOM snapshots.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
