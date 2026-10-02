import * as monaco from 'monaco-editor';
import { api, getLanguageSocketUrl } from '../../api/client';
import { toEditorRange, workspaceSourcePath } from './languageProtocol';

type Position = { line: number; character: number };
type Range = { start: Position; end: Position };
type Location = { uri?: string; range?: Range; targetUri?: string; targetSelectionRange?: Range };
type Diagnostic = { range: Range; message: string; severity?: number; code?: string | number };
type Completion = { label: string; kind?: number; detail?: string; insertText?: string; insertTextFormat?: number; sortText?: string; textEdit?: { newText: string; range?: Range }; additionalTextEdits?: { range: Range; newText: string }[] };

const editorRange = toEditorRange;
const position = (value: monaco.Position): Position => ({ line: value.lineNumber - 1, character: value.column - 1 });
const markdown = (content: unknown): monaco.IMarkdownString[] => {
  if (Array.isArray(content)) return content.flatMap(markdown);
  if (typeof content === 'string') return [{ value: content, isTrusted: false }];
  if (content && typeof content === 'object' && 'value' in content) {
    const item = content as { value: string; language?: string };
    return [{ value: item.language ? `\`\`\`${item.language}\n${item.value}\n\`\`\`` : item.value, isTrusted: false }];
  }
  return [];
};

export class PythonLanguageClient {
  private socket: WebSocket | null = null;
  private seq = 0;
  private closed = false;
  private ready = false;
  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: number }>();
  private disposables: monaco.IDisposable[] = [];
  private models = new Map<string, { model: monaco.editor.ITextModel; version: number; timer?: number; opened: boolean }>();
  private readonly prefix: string;

  constructor(private projectId: string, private onStatus: (status: string) => void, private onNavigate: (path: string, line: number) => Promise<void>, private onDiagnostics: (uri: string, diagnostics: Diagnostic[]) => void) {
    this.prefix = `qa-workspace://${projectId}/`;
  }

  private matches(model: monaco.editor.ITextModel) { return model.uri.toString().startsWith(this.prefix) && model.getLanguageId() === 'python'; }
  private notify(method: string, params: unknown) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ jsonrpc: '2.0', method, params }));
  }

  private request<T>(method: string, params: unknown): Promise<T> {
    if (this.socket?.readyState !== WebSocket.OPEN) return Promise.reject(new Error('Python language service is disconnected.'));
    const id = ++this.seq;
    return new Promise<T>((resolve, reject) => {
      const timer = window.setTimeout(() => { this.pending.delete(id); reject(new Error('Python language service request timed out.')); }, 15000);
      this.pending.set(id, { resolve: value => resolve(value as T), reject, timer });
      this.socket?.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }));
    });
  }

  private attachModel = (model: monaco.editor.ITextModel) => {
    if (!this.matches(model) || this.models.has(model.uri.toString())) return;
    const uri = model.uri.toString();
    const state = { model, version: 1, opened: false } as { model: monaco.editor.ITextModel; version: number; timer?: number; opened: boolean };
    this.models.set(uri, state);
    this.flush(uri);
    this.disposables.push(model.onDidChangeContent(() => {
      window.clearTimeout(state.timer);
      state.timer = window.setTimeout(() => this.flush(uri), 150);
    }), model.onWillDispose(() => {
      window.clearTimeout(state.timer);
      if (state.opened) this.notify('textDocument/didClose', { textDocument: { uri } });
      this.models.delete(uri);
      this.onDiagnostics(uri, []);
    }));
  };

  private flush(uri: string) {
    const state = this.models.get(uri);
    if (!this.ready || !state || state.model.isDisposed()) return;
    if (state.opened) {
      this.notify('textDocument/didChange', { textDocument: { uri, version: ++state.version }, contentChanges: [{ text: state.model.getValue() }] });
    } else {
      state.opened = true;
      this.notify('textDocument/didOpen', { textDocument: { uri, version: state.version, languageId: 'python', text: state.model.getValue() } });
    }
    window.clearTimeout(state.timer);
    state.timer = undefined;
  }

  private async query<T>(method: string, model: monaco.editor.ITextModel, at: monaco.Position, extra = {}): Promise<T | null> {
    if (!this.ready || !this.matches(model)) return null;
    const uri = model.uri.toString();
    if (this.models.get(uri)?.timer) this.flush(uri);
    try { return await this.request<T>(method, { textDocument: { uri }, position: position(at), ...extra }); }
    catch { return null; }
  }

  async start() {
    this.onStatus('connecting');
    try {
      const [ticket, url] = await Promise.all([api.createStreamTicket('lsp', this.projectId), getLanguageSocketUrl(this.projectId)]);
      if (this.closed) return;
      const socket = new WebSocket(url);
      this.socket = socket;
      socket.onopen = async () => {
        try {
          socket.send(JSON.stringify({ type: 'auth', stream_ticket: ticket }));
          await this.request('initialize', { capabilities: {
            textDocument: { completion: { completionItem: { snippetSupport: true } }, hover: { contentFormat: ['markdown', 'plaintext'] }, definition: { linkSupport: true }, publishDiagnostics: { versionSupport: true } },
            workspace: { configuration: true },
          }, clientInfo: { name: 'ai-qa-platform' } });
          if (this.closed) return;
          this.notify('initialized', {});
          this.ready = true;
          this.onStatus('connected');
          for (const uri of this.models.keys()) this.flush(uri);
        } catch { if (!this.closed) this.onStatus('error'); }
      };
      socket.onmessage = event => {
        let message: { id?: number; result?: unknown; error?: { message?: string }; method?: string; params?: { uri?: string; diagnostics?: Diagnostic[]; version?: number; type?: number } };
        try { message = JSON.parse(String(event.data)); } catch { return; }
        if (typeof message.id === 'number') {
          const pending = this.pending.get(message.id);
          if (!pending) return;
          window.clearTimeout(pending.timer);
          this.pending.delete(message.id);
          if (message.error) pending.reject(new Error(message.error.message || 'Python language service error'));
          else pending.resolve(message.result);
        } else if (message.method === 'textDocument/publishDiagnostics' && message.params?.uri?.startsWith(this.prefix)) {
          const state = this.models.get(message.params.uri);
          if (!state || state.model.isDisposed() || (message.params.version !== undefined && message.params.version < state.version)) return;
          const diagnostics = message.params.diagnostics ?? [];
          monaco.editor.setModelMarkers(state.model, 'basedpyright', diagnostics.map(item => ({
            ...editorRange(item.range), message: item.message, code: String(item.code ?? ''),
            severity: item.severity === 1 ? monaco.MarkerSeverity.Error : item.severity === 2 ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Info,
          })));
          this.onDiagnostics(message.params.uri, diagnostics);
        } else if (message.method === 'window/logMessage' && message.params?.type === 1) this.onStatus('error');
      };
      socket.onerror = socket.onclose = () => {
        this.ready = false;
        for (const pending of this.pending.values()) { window.clearTimeout(pending.timer); pending.reject(new Error('Python language service disconnected.')); }
        this.pending.clear();
        if (!this.closed) this.onStatus('error');
      };
      monaco.editor.getModels().forEach(this.attachModel);
      this.disposables.push(monaco.editor.onDidCreateModel(this.attachModel));
      this.registerProviders();
    } catch { if (!this.closed) this.onStatus('error'); }
  }

  private registerProviders() {
    this.disposables.push(monaco.languages.registerHoverProvider('python', {
      provideHover: async (model, at) => {
        const result = await this.query<{ contents: unknown; range?: Range }>('textDocument/hover', model, at);
        return result ? { contents: markdown(result.contents), range: result.range ? editorRange(result.range) : undefined } : null;
      },
    }), monaco.languages.registerCompletionItemProvider('python', {
      triggerCharacters: ['.'],
      provideCompletionItems: async (model, at) => {
        const result = await this.query<Completion[] | { items: Completion[]; isIncomplete?: boolean }>('textDocument/completion', model, at);
        const entries = Array.isArray(result) ? result : result?.items ?? [];
        const word = model.getWordUntilPosition(at);
        return { suggestions: entries.map(item => ({
          label: item.label, kind: item.kind === 3 ? monaco.languages.CompletionItemKind.Function : item.kind === 7 ? monaco.languages.CompletionItemKind.Class : monaco.languages.CompletionItemKind.Variable,
          detail: item.detail, sortText: item.sortText, insertText: item.textEdit?.newText ?? item.insertText ?? item.label,
          insertTextRules: item.insertTextFormat === 2 ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet : undefined,
          range: item.textEdit?.range ? editorRange(item.textEdit.range) : { startLineNumber: at.lineNumber, endLineNumber: at.lineNumber, startColumn: word.startColumn, endColumn: word.endColumn },
          additionalTextEdits: item.additionalTextEdits?.map(edit => ({ range: editorRange(edit.range), text: edit.newText })),
        })), incomplete: !Array.isArray(result) && Boolean(result?.isIncomplete) };
      },
    }), monaco.languages.registerDefinitionProvider('python', {
      provideDefinition: async (model, at) => {
        const result = await this.query<Location | Location[]>('textDocument/definition', model, at);
        return this.locations(result);
      },
    }), monaco.languages.registerReferenceProvider('python', {
      provideReferences: async (model, at) => {
        const result = await this.query<Location[]>('textDocument/references', model, at, { context: { includeDeclaration: true } });
        return this.locations(result);
      },
    }), monaco.editor.registerEditorOpener({
      openCodeEditor: async (_source, resource, selection) => {
        const path = workspaceSourcePath(resource.toString(), this.projectId);
        if (!path) return false;
        const line = selection && 'startLineNumber' in selection ? selection.startLineNumber : selection && 'lineNumber' in selection ? selection.lineNumber : 1;
        await this.onNavigate(path, line);
        return true;
      },
    }));
  }

  private locations(result: Location | Location[] | null): monaco.languages.Location[] {
    return (Array.isArray(result) ? result : result ? [result] : []).flatMap(item => {
      const uri = item.uri || item.targetUri;
      const range = item.range || item.targetSelectionRange;
      return uri && workspaceSourcePath(uri, this.projectId) && range ? [{ uri: monaco.Uri.parse(uri), range: editorRange(range) }] : [];
    });
  }

  dispose() {
    this.closed = true;
    this.ready = false;
    this.socket?.close();
    for (const state of this.models.values()) { window.clearTimeout(state.timer); if (!state.model.isDisposed()) monaco.editor.setModelMarkers(state.model, 'basedpyright', []); }
    for (const pending of this.pending.values()) { window.clearTimeout(pending.timer); pending.reject(new Error('Python language service closed.')); }
    this.pending.clear();
    this.models.clear();
    this.disposables.forEach(item => item.dispose());
  }
}
