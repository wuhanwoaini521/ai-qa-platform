import React, { useEffect, useRef, useState } from 'react';
import '../monaco';
import { useTranslation } from 'react-i18next';
import Editor, { OnMount } from '@monaco-editor/react';
import { FileCode } from 'lucide-react';
import { Breakpoint, GitDiffResult } from '../../../types';
import { EditorTab } from '../types';
import { PythonLanguageClient } from '../pythonLanguageClient';
import { usePreferences } from '../../../app/Preferences';

/** Monaco instance handed to `onMount`; `monaco-editor` is not a direct dependency, so the type is derived. */
export type MonacoEditorInstance = Parameters<OnMount>[0];

interface MonacoEditorPaneProps {
  projectId?: string | null;
  onNavigateToSource?: (path: string, line: number) => Promise<void>;
  onAIAction?: (action: string) => void;
  onLanguageDiagnostics?: (uri: string, diagnostics: Array<{ range: { start: { line: number; character: number }; end: { line: number; character: number } }; message: string; severity?: number }>) => void;
  activeTab: EditorTab | undefined;
  loadingFile: boolean;
  showDiffView: boolean;
  diffResult: GitDiffResult;
  /** Imperative handle shared with the problems panel and the QA assistant. */
  editorRef: React.RefObject<MonacoEditorInstance | null>;
  onEditorReady?: () => void;
  stickyScroll?: boolean;
  onChange: (value: string | undefined) => void;
  breakpoints?: Breakpoint[];
  onToggleBreakpoint?: (filePath: string, lineNumber: number) => void;
  initialFocusLineNumber?: number;
  executionLocation?: { path: string; line: number } | null;
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
  projectId,
  onNavigateToSource,
  onAIAction,
  onLanguageDiagnostics,
  activeTab,
  loadingFile,
  showDiffView,
  diffResult,
  editorRef,
  onEditorReady,
  stickyScroll = true,
  onChange,
  breakpoints = [],
  onToggleBreakpoint,
  initialFocusLineNumber,
  executionLocation,
}) => {
  const { t } = useTranslation('studioShell');
  const { theme } = usePreferences();
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setSystemDark(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const [editorReady, setEditorReady] = useState(false);
  const [editorMountVersion, setEditorMountVersion] = useState(0);
  const [languageStatus, setLanguageStatus] = useState('connecting');
  const navigateRef = useRef(onNavigateToSource);
  const diagnosticsRef = useRef(onLanguageDiagnostics);
  const aiActionRef = useRef(onAIAction);
  navigateRef.current = onNavigateToSource;
  diagnosticsRef.current = onLanguageDiagnostics;
  aiActionRef.current = onAIAction;
  const decorationIds = useRef<string[]>([]);
  const focusDecorationIds = useRef<string[]>([]);
  const executionDecorationIds = useRef<string[]>([]);
  const toggleRef = useRef(onToggleBreakpoint);
  const activePathRef = useRef(activeTab?.path ?? '');
  toggleRef.current = onToggleBreakpoint;
  activePathRef.current = activeTab?.path ?? '';

  const handleEditorDidMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    setEditorReady(true);
    setEditorMountVersion((version) => version + 1);
    editor.onMouseDown((event) => {
      const target = event.target.type;
      if (
        (target === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN ||
          target === monaco.editor.MouseTargetType.GUTTER_LINE_NUMBERS) &&
        event.target.position
      ) {
        toggleRef.current?.(activePathRef.current, event.target.position.lineNumber);
      }
    });
    if (aiActionRef.current) for (const [index, action] of ['explain', 'fix', 'refactor', 'generate_test', 'add_assertion', 'improve_locator', 'analyze_failure', 'optimize'].entries()) {
      editor.addAction({ id: `qa-ai-${action}`, label: t(`lsp.actions.${action}`), contextMenuGroupId: 'qa-ai', contextMenuOrder: index,
        run: () => { aiActionRef.current?.(action); } });
    }
    onEditorReady?.();
  };

  useEffect(() => {
    if (!projectId || !editorReady) return;
    const client = new PythonLanguageClient(projectId, setLanguageStatus,
      (path, line) => navigateRef.current?.(path, line) ?? Promise.resolve(),
      (uri, diagnostics) => diagnosticsRef.current?.(uri, diagnostics));
    void client.start();
    return () => client.dispose();
  }, [projectId, editorReady, editorMountVersion]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editorReady || loadingFile || !editor || !activeTab?.path) return;
    const filePath = activeTab.path.replace(/\\/g, '/').replace(/^\/+/, '');
    const breakpointsByLine = new Map<number, Breakpoint>();
    for (const item of breakpoints) {
      if (!item.enabled || item.file_path.replace(/\\/g, '/') !== filePath) continue;
      const existing = breakpointsByLine.get(item.line_number);
      if (!existing || (existing.source === 'auto_failure' && item.source === 'manual')) {
        breakpointsByLine.set(item.line_number, item);
      }
    }
    const decorations = [...breakpointsByLine.values()].map((item) => ({
        range: {
          startLineNumber: item.line_number,
          endLineNumber: item.line_number,
          startColumn: 1,
          endColumn: 1,
        },
        options: {
          isWholeLine: false,
          glyphMarginClassName: `qa-breakpoint-glyph qa-breakpoint-${item.source === 'auto_failure' ? 'auto' : 'manual'}`,
          glyphMarginHoverMessage: { value: item.source === 'auto_failure' ? 'Auto failure breakpoint' : 'Manual breakpoint' },
        },
      }));
    decorationIds.current = editor.deltaDecorations(decorationIds.current, decorations);
  }, [activeTab?.path, breakpoints, editorMountVersion, editorReady, editorRef, loadingFile]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editorReady || loadingFile || !editor || !activeTab || !initialFocusLineNumber || initialFocusLineNumber < 1) return;
    const lineNumber = Math.min(initialFocusLineNumber, editor.getModel()?.getLineCount() ?? initialFocusLineNumber);
    editor.revealLineInCenter(lineNumber);
    editor.setPosition({ lineNumber, column: 1 });
    focusDecorationIds.current = editor.deltaDecorations(focusDecorationIds.current, [{
      range: { startLineNumber: lineNumber, endLineNumber: lineNumber, startColumn: 1, endColumn: 1 },
      options: { isWholeLine: true, className: 'qa-failure-line' },
    }]);
  }, [activeTab?.path, editorMountVersion, editorReady, editorRef, initialFocusLineNumber, loadingFile]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editorReady || loadingFile || !editor || !activeTab?.path || !executionLocation) {
      if (editor) executionDecorationIds.current = editor.deltaDecorations(executionDecorationIds.current, []);
      return;
    }
    const activePath = activeTab.path.replace(/\\/g, '/').replace(/^\/+/, '');
    const executionPath = executionLocation.path.replace(/\\/g, '/').replace(/^\/+/, '');
    if (activePath !== executionPath) {
      executionDecorationIds.current = editor.deltaDecorations(executionDecorationIds.current, []);
      return;
    }
    const lineNumber = Math.min(executionLocation.line, editor.getModel()?.getLineCount() ?? executionLocation.line);
    editor.revealLineInCenter(lineNumber);
    executionDecorationIds.current = editor.deltaDecorations(executionDecorationIds.current, [{
      range: { startLineNumber: lineNumber, endLineNumber: lineNumber, startColumn: 1, endColumn: 1 },
      options: {
        isWholeLine: true,
        className: 'qa-debug-execution-line',
        glyphMarginClassName: 'qa-debug-execution-glyph',
      },
    }]);
  }, [activeTab?.path, editorMountVersion, editorReady, editorRef, executionLocation, loadingFile]);

  return (
    <div style={{ height: '100%', position: 'relative', overflow: 'hidden' }}>
      {showDiffView ? (
        <div
          style={{
            height: '100%',
            overflowY: 'auto',
            padding: '16px',
            background: 'var(--surface-inverse, #1b1b1d)',
            color: 'var(--ink-inverse)',
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
          }}
        >
          <div style={{ marginBottom: '10px', color: 'var(--ink-faint)', fontSize: '11px', textTransform: 'uppercase' }}>
            {t('editor.gitDiffTitle')}
          </div>
          <pre style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
            {diffResult.diff || t('editor.noUncommittedChanges')}
          </pre>
        </div>
      ) : loadingFile ? (
        <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
          {t('editor.loadingFile')}
        </div>
      ) : activeTab ? (
        <Editor
          path={projectId ? `qa-workspace://${projectId}/${activeTab.path.split('/').map(encodeURIComponent).join('/')}` : undefined}
          height="100%"
          language={getLanguage(activeTab.path)}
          value={activeTab.content}
          theme={theme === 'dark' || (theme === 'system' && systemDark) ? 'vs-dark' : 'light'}
          onMount={handleEditorDidMount}
          options={{
            fontSize: 15,
            fontFamily: "'JetBrains Mono', Consolas, Menlo, monospace",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            stickyScroll: { enabled: stickyScroll },
            lineNumbers: 'on',
            glyphMargin: true,
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
          <div style={{ fontSize: '14px', fontWeight: 500 }}>{t('editor.emptySelectFile')} <code>Cmd+P</code></div>
          <div style={{ fontSize: '12px', marginTop: '4px' }}>
            {t('editor.emptyHint')}
          </div>
        </div>
      )}
      {projectId && activeTab?.path.endsWith('.py') && (
        <span role="status" style={{ position: 'absolute', right: 14, bottom: 4, padding: '3px 7px', borderRadius: 6, background: 'var(--ui-surface-raised)', color: languageStatus === 'error' ? 'var(--ui-rose)' : 'var(--text-muted)', fontSize: 11 }}>
          {t(`lsp.status.${languageStatus}`)}
        </span>
      )}
    </div>
  );
};
