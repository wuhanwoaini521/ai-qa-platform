/**
 * Layout and tone rules for the agent execution tree.
 *
 * The tree is a left-to-right layering of real rows: the task, the steps it ran, and beside each
 * step the activities it caused (model calls, evidence, artifacts) plus anything the task produced
 * (runs, suggestions). Everything here is pure so the layout can be tested without a DOM.
 */
import type { ExecutionTrace, TraceNode, TraceNodeType } from '../../types/executionTrace';

export const TREE_COLUMN_WIDTH = 236;
export const TREE_COLUMN_GAP = 76;
export const TREE_ROW_HEIGHT = 104;
export const TREE_NODE_HEIGHT = 84;

export type TreeTone = 'ok' | 'active' | 'attention' | 'bad' | 'idle';

const OK = new Set(['COMPLETED', 'PASSED', 'SUCCESS', 'VERIFIED', 'APPROVED', 'READY']);
const LIVE = new Set(['RUNNING', 'QUEUED', 'VERIFYING', 'STARTED', 'IN_PROGRESS']);
const WAITING = new Set(['PENDING', 'WAITING', 'WAITING_FOR_APPROVAL']);
const BAD = new Set(['FAILED', 'BLOCKED', 'CANCELLED', 'TIMEOUT', 'INTERRUPTED', 'REJECTED', 'STOPPED']);

export function treeTone(status: string | null | undefined): TreeTone {
  const value = (status ?? '').toUpperCase();
  if (OK.has(value)) return 'ok';
  if (LIVE.has(value)) return 'active';
  if (WAITING.has(value)) return 'attention';
  if (BAD.has(value)) return 'bad';
  return 'idle';
}

/** The four states the tree has to make obvious at a glance. */
export function treeStateLabel(status: string | null | undefined): 'running' | 'done' | 'failed' | 'waiting' | 'unknown' {
  const tone = treeTone(status);
  if (tone === 'active') return 'running';
  if (tone === 'ok') return 'done';
  if (tone === 'bad') return 'failed';
  if (tone === 'attention') return 'waiting';
  return 'unknown';
}

export function traceIsLive(trace: ExecutionTrace | null): boolean {
  if (!trace) return false;
  return trace.nodes.some((node) => treeTone(node.status) === 'active' || treeTone(node.status) === 'attention');
}

export function columnX(depth: number): number {
  return depth * (TREE_COLUMN_WIDTH + TREE_COLUMN_GAP);
}

/** Depth comes from the recorded parent link only; a node without one is a root. */
export function nodeDepths(trace: ExecutionTrace): Map<string, number> {
  const byId = new Map(trace.nodes.map((node) => [node.id, node]));
  const depths = new Map<string, number>();
  const resolve = (node: TraceNode, seen: Set<string>): number => {
    const known = depths.get(node.id);
    if (known !== undefined) return known;
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
    if (!parent || seen.has(node.id)) {
      depths.set(node.id, 0);
      return 0;
    }
    seen.add(node.id);
    const depth = resolve(parent, seen) + 1;
    depths.set(node.id, depth);
    return depth;
  };
  for (const node of trace.nodes) resolve(node, new Set());
  return depths;
}

export function descendantsOf(trace: ExecutionTrace, nodeId: string): Set<string> {
  const children = new Map<string, string[]>();
  for (const node of trace.nodes) {
    if (!node.parent_id) continue;
    const list = children.get(node.parent_id) ?? [];
    list.push(node.id);
    children.set(node.parent_id, list);
  }
  const out = new Set<string>();
  const walk = (id: string) => {
    for (const child of children.get(id) ?? []) {
      if (out.has(child)) continue;
      out.add(child);
      walk(child);
    }
  };
  walk(nodeId);
  return out;
}

export interface TreeLayoutOptions {
  collapsed?: ReadonlySet<string>;
  focusId?: string | null;
}

export interface TreeCardData extends Record<string, unknown> {
  node: TraceNode;
  tone: TreeTone;
  state: string;
  onToggle: () => void;
  collapsed: boolean;
  hasChildren: boolean;
}

export interface TreeCard {
  id: string;
  type: 'traceNode';
  position: { x: number; y: number };
  data: TreeCardData;
  initialWidth: number;
  initialHeight: number;
}

export interface TreeEdge {
  id: string;
  source: string;
  target: string;
  type: 'smoothstep';
  animated: boolean;
  label: string;
  className: string;
}

/**
 * Lay the tree out by depth, ordered within a column by start time so parallel activities keep a
 * stable reading order across refreshes.
 */
export function treeNodes(
  trace: ExecutionTrace,
  options: TreeLayoutOptions = {},
  onToggle?: (nodeId: string) => void,
): TreeCard[] {
  const depths = nodeDepths(trace);
  const hidden = new Set<string>();
  for (const id of options.collapsed ?? []) {
    for (const child of descendantsOf(trace, id)) hidden.add(child);
  }
  let visible = trace.nodes.filter((node) => !hidden.has(node.id));
  if (options.focusId) {
    const keep = descendantsOf(trace, options.focusId);
    const byId = new Map(trace.nodes.map((node) => [node.id, node]));
    let cursor = byId.get(options.focusId)?.parent_id ?? null;
    keep.add(options.focusId);
    while (cursor) {
      keep.add(cursor);
      cursor = byId.get(cursor)?.parent_id ?? null;
    }
    visible = visible.filter((node) => keep.has(node.id));
  }
  const children = new Map<string, number>();
  for (const node of trace.nodes) {
    if (!node.parent_id) continue;
    children.set(node.parent_id, (children.get(node.parent_id) ?? 0) + 1);
  }
  const rows = new Map<number, number>();
  const ordered = [...visible].sort((a, b) => {
    const depthA = depths.get(a.id) ?? 0;
    const depthB = depths.get(b.id) ?? 0;
    if (depthA !== depthB) return depthA - depthB;
    const startedA = a.started_at ?? '';
    const startedB = b.started_at ?? '';
    if (startedA !== startedB) return startedA < startedB ? -1 : 1;
    return a.id < b.id ? -1 : 1;
  });
  return ordered.map((node) => {
    const depth = depths.get(node.id) ?? 0;
    const row = rows.get(depth) ?? 0;
    rows.set(depth, row + 1);
    const childCount = children.get(node.id) ?? 0;
    return {
      id: node.id,
      type: 'traceNode',
      position: { x: columnX(depth), y: row * TREE_ROW_HEIGHT },
      initialWidth: TREE_COLUMN_WIDTH,
      initialHeight: TREE_NODE_HEIGHT,
      data: {
        node,
        tone: treeTone(node.status),
        state: treeStateLabel(node.status),
        collapsed: Boolean(options.collapsed?.has(node.id)),
        hasChildren: childCount > 0,
        onToggle: () => onToggle?.(node.id),
      },
    };
  });
}

export function treeEdges(trace: ExecutionTrace, visible: ReadonlySet<string>): TreeEdge[] {
  return trace.edges
    .filter((edge) => visible.has(edge.source) && visible.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep' as const,
      // Only a live hand-off animates; a finished trajectory stays still.
      animated: false,
      label: edge.type,
      className: `let-edge is-${edge.type.toLowerCase()}`,
    }));
}

export function traceExtent(cards: TreeCard[]): { right: number; bottom: number } {
  let right = 0;
  let bottom = 0;
  for (const card of cards) {
    right = Math.max(right, card.position.x + TREE_COLUMN_WIDTH);
    bottom = Math.max(bottom, card.position.y + TREE_NODE_HEIGHT);
  }
  return { right, bottom };
}

/** Duration in the largest unit that still reads as a number ("3.4s", "1m 12s"). */
export function formatDuration(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds - minutes * 60)}s`;
}

export function nodeKindLabel(node: TraceNode): string {
  return node.type;
}

export const TRACE_KIND_ORDER: TraceNodeType[] = ['task', 'step', 'invocation', 'evidence', 'artifact', 'run', 'suggestion'];
