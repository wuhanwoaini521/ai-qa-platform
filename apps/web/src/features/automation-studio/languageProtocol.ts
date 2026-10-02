export type ProtocolPosition = { line: number; character: number };
export type ProtocolRange = { start: ProtocolPosition; end: ProtocolPosition };

export function toEditorRange(range: ProtocolRange) {
  return { startLineNumber: range.start.line + 1, startColumn: range.start.character + 1, endLineNumber: range.end.line + 1, endColumn: range.end.character + 1 };
}

export function workspaceSourcePath(uri: string, projectId: string): string | null {
  try {
    if (!uri.startsWith(`qa-workspace://${projectId}/`)) return null;
    const path = decodeURIComponent(uri.slice(`qa-workspace://${projectId}/`.length));
    if (!path.endsWith('.py') || /[\\:#?\u0000]/.test(path) || path.split('/').some(part => part === '..' || part === '.' || !part)) return null;
    return path;
  } catch { return null; }
}
