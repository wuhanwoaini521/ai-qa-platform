import React from 'react';
import Editor, { OnMount } from '@monaco-editor/react';
import { FileCode } from 'lucide-react';
import { GitDiffResult } from '../../../types';
import { EditorTab } from '../types';

/** Monaco instance handed to `onMount`; `monaco-editor` is not a direct dependency, so the type is derived. */
export type MonacoEditorInstance = Parameters<OnMount>[0];

interface MonacoEditorPaneProps {
  activeTab: EditorTab | undefined;
  loadingFile: boolean;
  showDiffView: boolean;
  diffResult: GitDiffResult;
  /** Imperative handle shared with the problems panel and the QA assistant. */
  editorRef: React.RefObject<MonacoEditorInstance | null>;
  onChange: (value: string | undefined) => void;
}

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

export const MonacoEditorPane: React.FC<MonacoEditorPaneProps> = ({
  activeTab,
  loadingFile,
  showDiffView,
  diffResult,
  editorRef,
  onChange,
}) => {
  const handleEditorDidMount: OnMount = (editor) => {
    editorRef.current = editor;
  };

  return (
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
          onChange={onChange}
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
  );
};
