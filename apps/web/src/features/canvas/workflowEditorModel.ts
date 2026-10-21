/**
 * Pure editing model for a QA workflow draft.
 *
 * The server owns validation; this module only keeps the editor honest — it refuses the edits that
 * can never be valid (self links, cycles, duplicate links, unknown kinds) and gives every draft an
 * undo history. Nothing here ever contacts the runtime.
 */
import type {
  WorkflowCatalogueEntry,
  WorkflowEdgeSpec,
  WorkflowGraphSpec,
  WorkflowIssue,
  WorkflowNodeSpec,
} from '../../types/workflowDefinition';

export const EDITOR_COLUMN_WIDTH = 268;
export const EDITOR_ROW_HEIGHT = 132;
export const EDITOR_ORIGIN_X = 40;
export const EDITOR_ORIGIN_Y = 40;

export interface EditorState {
  nodes: WorkflowNodeSpec[];
  edges: WorkflowEdgeSpec[];
}

export interface EditorHistory {
  past: EditorState[];
  present: EditorState;
  future: EditorState[];
}

export type EditorError = 'self_link' | 'duplicate_link' | 'cycle' | 'unknown_kind' | 'missing_node';

export function emptyEditor(graph?: WorkflowGraphSpec): EditorHistory {
  return { past: [], present: normalise(graph ?? { nodes: [], edges: [] }), future: [] };
}

export function normalise(graph: WorkflowGraphSpec): EditorState {
  return {
    nodes: graph.nodes.map((node) => ({ ...node, inputs: { ...(node.inputs ?? {}) } })),
    edges: graph.edges.map((edge) => ({ source: edge.source, target: edge.target })),
  };
}

export function sameGraph(left: EditorState, right: EditorState): boolean {
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

function canonical(state: EditorState): unknown {
  return {
    nodes: [...state.nodes]
      .sort((a, b) => a.key.localeCompare(b.key))
      .map((node) => ({
        key: node.key,
        kind: node.kind,
        title: node.title ?? '',
        inputs: Object.fromEntries(Object.entries(node.inputs ?? {}).sort(([a], [b]) => a.localeCompare(b))),
        // Layout is view state: dragging a card or re-running auto layout must not look like an unsaved edit.
      })),
    edges: [...state.edges]
      .map((edge) => `${edge.source}->${edge.target}`)
      .sort((a, b) => a.localeCompare(b)),
  };
}

/** Where the cards sit. Kept apart from `sameGraph` so a drag is saveable without looking like a graph edit. */
export function sameLayout(left: EditorState, right: EditorState): boolean {
  const positions = (state: EditorState) =>
    JSON.stringify(
      [...state.nodes]
        .sort((a, b) => a.key.localeCompare(b.key))
        .map((node) => [node.key, Math.round(node.position?.x ?? 0), Math.round(node.position?.y ?? 0)]),
    );
  return positions(left) === positions(right);
}

export function applyEdit(history: EditorHistory, next: EditorState): EditorHistory {
  if (sameGraph(history.present, next)) {
    return history;
  }
  return { past: [...history.past, history.present].slice(-80), present: next, future: [] };
}

export function undo(history: EditorHistory): EditorHistory {
  const previous = history.past[history.past.length - 1];
  if (!previous) {
    return history;
  }
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future].slice(0, 80),
  };
}

export function redo(history: EditorHistory): EditorHistory {
  const [next, ...rest] = history.future;
  if (!next) {
    return history;
  }
  return { past: [...history.past, history.present].slice(-80), present: next, future: rest };
}

/** A stable, readable key: the last segment of the kind, numbered when it is already taken. */
export function nextNodeKey(kind: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  const base = (kind.split('.').pop() || 'node').replace(/[^a-z0-9_]/gi, '_').slice(0, 24) || 'node';
  if (!used.has(base)) {
    return base;
  }
  for (let index = 2; index < 500; index += 1) {
    const candidate = `${base}_${index}`;
    if (!used.has(candidate)) {
      return candidate;
    }
  }
  return `${base}_${used.size + 1}`;
}

export function addNode(
  state: EditorState,
  catalogue: WorkflowCatalogueEntry[],
  kind: string,
): { state: EditorState; key: string } | { error: EditorError } {
  const entry = catalogue.find((item) => item.kind === kind);
  if (!entry) {
    return { error: 'unknown_kind' };
  }
  const key = nextNodeKey(kind, state.nodes.map((node) => node.key));
  const depth = state.nodes.length;
  const node: WorkflowNodeSpec = {
    key,
    kind,
    title: entry.title,
    inputs: {},
    position: {
      x: EDITOR_ORIGIN_X + (depth % 3) * EDITOR_COLUMN_WIDTH,
      y: EDITOR_ORIGIN_Y + Math.floor(depth / 3) * EDITOR_ROW_HEIGHT,
    },
  };
  return { state: { nodes: [...state.nodes, node], edges: state.edges }, key };
}

export function removeNode(state: EditorState, key: string): EditorState {
  return {
    nodes: state.nodes.filter((node) => node.key !== key),
    edges: state.edges.filter((edge) => edge.source !== key && edge.target !== key),
  };
}

export function updateNode(state: EditorState, key: string, patch: Partial<WorkflowNodeSpec>): EditorState {
  return {
    ...state,
    nodes: state.nodes.map((node) => (node.key === key ? { ...node, ...patch } : node)),
  };
}

export function setInput(state: EditorState, key: string, name: string, value: unknown): EditorState {
  const node = state.nodes.find((item) => item.key === key);
  if (!node) {
    return state;
  }
  const inputs = { ...(node.inputs ?? {}) };
  if (value === '' || value === undefined || value === null) {
    delete inputs[name];
  } else {
    inputs[name] = value;
  }
  return updateNode(state, key, { inputs });
}

/** The one reference syntax the runtime understands: bind a value from the task's own inputs. */
export function inputReference(inputName: string): Record<string, string> {
  return { $input: inputName };
}

export function describeInput(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }
  if (typeof value === 'object' && value !== null && '$input' in (value as Record<string, unknown>)) {
    return `$input.${String((value as Record<string, unknown>).$input)}`;
  }
  if (typeof value === 'string') {
    return value;
  }
  return JSON.stringify(value);
}

/** Parse what the user typed: `$input.name` becomes a real binding, everything else stays literal. */
export function parseInput(raw: string, kind: 'string' | 'integer' | 'boolean' | 'list'): unknown {
  const trimmed = raw.trim();
  if (!trimmed) {
    return '';
  }
  if (trimmed.startsWith('$input.')) {
    return inputReference(trimmed.slice('$input.'.length));
  }
  if (kind === 'integer') {
    const parsed = Number.parseInt(trimmed, 10);
    return Number.isNaN(parsed) ? trimmed : parsed;
  }
  if (kind === 'boolean') {
    return trimmed === 'true';
  }
  if (kind === 'list') {
    return trimmed
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return trimmed;
}

function reaches(edges: WorkflowEdgeSpec[], from: string, to: string): boolean {
  const seen = new Set<string>();
  const stack = [from];
  while (stack.length) {
    const current = stack.pop() as string;
    if (current === to) {
      return true;
    }
    if (seen.has(current)) {
      continue;
    }
    seen.add(current);
    for (const edge of edges) {
      if (edge.source === current) {
        stack.push(edge.target);
      }
    }
  }
  return false;
}

export function connect(
  state: EditorState,
  source: string,
  target: string,
): { state: EditorState } | { error: EditorError } {
  if (!state.nodes.some((node) => node.key === source) || !state.nodes.some((node) => node.key === target)) {
    return { error: 'missing_node' };
  }
  if (source === target) {
    return { error: 'self_link' };
  }
  if (state.edges.some((edge) => edge.source === source && edge.target === target)) {
    return { error: 'duplicate_link' };
  }
  // The new link closes a loop when the source is already reachable from the target.
  if (reaches(state.edges, target, source)) {
    return { error: 'cycle' };
  }
  return { state: { nodes: state.nodes, edges: [...state.edges, { source, target }] } };
}

export function disconnect(state: EditorState, source: string, target: string): EditorState {
  return {
    ...state,
    edges: state.edges.filter((edge) => !(edge.source === source && edge.target === target)),
  };
}

export function depths(state: EditorState): Map<string, number> {
  const parents = new Map<string, string[]>(state.nodes.map((node) => [node.key, []]));
  for (const edge of state.edges) {
    parents.get(edge.target)?.push(edge.source);
  }
  const result = new Map<string, number>();
  const visiting = new Set<string>();
  const depthOf = (key: string): number => {
    if (result.has(key)) {
      return result.get(key) as number;
    }
    if (visiting.has(key)) {
      return 0;
    }
    visiting.add(key);
    const list = parents.get(key) ?? [];
    const value = list.length ? Math.max(...list.map((parent) => depthOf(parent) + 1)) : 0;
    visiting.delete(key);
    result.set(key, value);
    return value;
  };
  for (const node of state.nodes) {
    depthOf(node.key);
  }
  return result;
}

/** Longest-path layering, declaration order inside a layer: stable, readable, no overlap. */
export function autoLayout(state: EditorState): EditorState {
  const level = depths(state);
  const rows = new Map<number, number>();
  return {
    ...state,
    nodes: state.nodes.map((node) => {
      const column = level.get(node.key) ?? 0;
      const row = rows.get(column) ?? 0;
      rows.set(column, row + 1);
      return {
        ...node,
        position: {
          x: EDITOR_ORIGIN_X + column * EDITOR_COLUMN_WIDTH,
          y: EDITOR_ORIGIN_Y + row * EDITOR_ROW_HEIGHT,
        },
      };
    }),
  };
}

/**
 * Local checks that mirror the server rules so the editor can answer instantly. The server stays
 * authoritative: what it returns replaces whatever this produces.
 */
export function localIssues(state: EditorState, catalogue: WorkflowCatalogueEntry[]): WorkflowIssue[] {
  const issues: WorkflowIssue[] = [];
  const known = new Set(catalogue.map((entry) => entry.kind));
  if (state.nodes.length === 0) {
    issues.push({ code: 'EMPTY_GRAPH', message: 'A workflow needs at least one node.' });
  }
  for (const node of state.nodes) {
    if (!known.has(node.kind)) {
      issues.push({ code: 'UNKNOWN_KIND', message: `Unknown node kind "${node.kind}".`, node_key: node.key });
      continue;
    }
    const entry = catalogue.find((item) => item.kind === node.kind);
    for (const input of entry?.inputs ?? []) {
      if (input.required && !((node.inputs ?? {})[input.name] !== undefined)) {
        issues.push({
          code: 'MISSING_INPUT',
          message: `Node "${node.key}" needs ${input.name}.`,
          node_key: node.key,
        });
      }
    }
  }
  const approvals = state.nodes.filter((node) => node.kind === 'task.request_approval').map((node) => node.key);
  const writes = state.nodes.filter((node) => catalogue.find((entry) => entry.kind === node.kind)?.writes);
  for (const node of writes) {
    const guarded = approvals.some((approval) => reaches(state.edges, approval, node.key));
    if (!guarded) {
      issues.push({
        code: 'WRITE_WITHOUT_APPROVAL',
        message: `Node "${node.key}" writes to the workspace, so an approval must run before it.`,
        node_key: node.key,
      });
    }
  }
  const visiting = new Set<string>();
  const done = new Set<string>();
  const cycleAt = (key: string): boolean => {
    if (done.has(key)) {
      return false;
    }
    if (visiting.has(key)) {
      return true;
    }
    visiting.add(key);
    for (const edge of state.edges) {
      if (edge.source === key && cycleAt(edge.target)) {
        return true;
      }
    }
    visiting.delete(key);
    done.add(key);
    return false;
  };
  if (state.nodes.some((node) => cycleAt(node.key))) {
    issues.push({ code: 'CYCLE', message: 'The graph contains a cycle.' });
  }
  return issues;
}

export function issueTone(code: string): 'bad' | 'attention' {
  return ['CYCLE', 'UNKNOWN_KIND', 'WRITE_WITHOUT_APPROVAL'].includes(code) ? 'bad' : 'attention';
}

export function riskLabel(risk: WorkflowCatalogueEntry['risk']): 'read' | 'write' | 'approval' | 'execute' {
  if (risk === 'WRITE') {
    return 'write';
  }
  if (risk === 'APPROVAL') {
    return 'approval';
  }
  if (risk === 'EXECUTE') {
    return 'execute';
  }
  return 'read';
}
