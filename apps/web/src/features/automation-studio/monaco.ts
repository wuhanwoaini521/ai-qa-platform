import * as monaco from 'monaco-editor';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker.js?worker';
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker.js?worker';
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker.js?worker';
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker.js?worker';
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker.js?worker';
import { loader } from '@monaco-editor/react';

type MonacoWorkerGlobal = typeof globalThis & {
  MonacoEnvironment: { getWorker: (_workerId: string, label: string) => Worker };
};

(globalThis as MonacoWorkerGlobal).MonacoEnvironment = {
  getWorker(_workerId, label) {
    if (label === 'json') return new jsonWorker();
    if (label === 'css' || label === 'scss' || label === 'less') return new cssWorker();
    if (label === 'html' || label === 'handlebars' || label === 'razor') return new htmlWorker();
    if (label === 'typescript' || label === 'javascript') return new tsWorker();
    return new editorWorker();
  },
};

// Bundling Monaco locally avoids the default CDN dependency and keeps the editor usable offline.
monaco.editor.defineTheme('graphite-workspace', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: '', foreground: 'E7EFEC', background: '111619' },
    { token: 'comment', foreground: '788985' },
    { token: 'string', foreground: 'A6D5C1' },
    { token: 'number', foreground: 'E6AE68' },
    { token: 'keyword', foreground: 'C3B6FF' },
    { token: 'type', foreground: '9BBEFF' },
  ],
  colors: {
    'editor.background': '#111619',
    'editor.foreground': '#E7EFEC',
    'editorLineNumber.foreground': '#788985',
    'editorLineNumber.activeForeground': '#A1B0AC',
    'editorCursor.foreground': '#A6D5C1',
    'editor.selectionBackground': '#263A35',
    'editor.inactiveSelectionBackground': '#263136',
    'editor.lineHighlightBackground': '#182226',
    'editorGutter.background': '#111619',
    'editorIndentGuide.background': '#29363B',
    'editorIndentGuide.activeBackground': '#405057',
    'editorWidget.background': '#1B2428',
    'editorWidget.border': '#344148',
    'editorSuggestWidget.background': '#1B2428',
    'editorSuggestWidget.border': '#344148',
    'editorSuggestWidget.selectedBackground': '#263136',
    'editorHoverWidget.background': '#1B2428',
    'editorHoverWidget.border': '#344148',
    'scrollbarSlider.background': '#53616866',
    'scrollbarSlider.hoverBackground': '#53616899',
    'scrollbarSlider.activeBackground': '#536168CC',
  },
});

loader.config({ monaco });
