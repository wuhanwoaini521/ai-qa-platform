import type { Edge, Node } from '@xyflow/react';
import type {
  DiscoveryMetrics,
  WorkflowCanvas,
  WorkflowNode,
  WorkflowStageKey,
} from '../../types/workflowCanvas';

/** Column per pipeline stage, one row per record: deterministic, so a reload keeps the same picture. */
export const CANVAS_COLUMN_WIDTH = 264;
export const CANVAS_COLUMN_GAP = 56;
export const CANVAS_ROW_HEIGHT = 104;
export const CANVAS_HEADER_HEIGHT = 64;

export type NodeTone = 'ok' | 'active' | 'attention' | 'bad' | 'idle';

export interface CanvasNodeData extends Record<string, unknown> {
  label: string;
  subtitle: string | null;
  status: string;
  tone: NodeTone;
  kind: WorkflowNode['kind'];
  entityId: string;
  /** Only discovery cards carry it: the evidence counts read from the server's analysis. */
  evidenceLine?: string;
}

export interface CanvasStageData extends Record<string, unknown> {
  title: string;
  count: number;
  description: string;
  /** Collapsing a stage hides its rows and keeps the column header, so text stays readable. */
  collapsed: boolean;
  onToggle: () => void;
}

const TONES: Record<string, NodeTone> = {
  PASSED: 'ok',
  COMPLETED: 'ok',
  VERIFIED: 'ok',
  ACTIVE: 'ok',
  READY: 'ok',
  RUNNING: 'active',
  QUEUED: 'active',
  PENDING: 'attention',
  WAITING: 'attention',
  WAITING_FOR_APPROVAL: 'attention',
  VERIFYING: 'active',
  BLOCKED: 'bad',
  FAILED: 'bad',
  CANCELLED: 'bad',
  TIMEOUT: 'bad',
  INTERRUPTED: 'bad',
  STOPPED: 'idle',
};

/** The server owns the status vocabulary; the canvas only decides how loud each value looks. */
export function statusTone(status: string): NodeTone {
  return TONES[status.toUpperCase()] ?? 'idle';
}

export function columnX(stageIndex: number): number {
  return stageIndex * (CANVAS_COLUMN_WIDTH + CANVAS_COLUMN_GAP);
}

export function flowNodes(
  canvas: WorkflowCanvas,
  options: { collapsed?: ReadonlySet<string>; onToggle?: (stage: string) => void } = {},
): Node<CanvasNodeData | CanvasStageData>[] {
  const collapsed = options.collapsed ?? new Set<string>();
  const columns = new Map<WorkflowStageKey, number>();
  canvas.stages.forEach((stage, index) => columns.set(stage.key, index));

  const stages: Node<CanvasStageData>[] = canvas.stages.map((stage, index) => ({
    id: `stage:${stage.key}`,
    type: 'stage',
    position: { x: columnX(index), y: 0 },
    data: {
      title: stage.title,
      count: canvas.nodes.filter((node) => node.stage === stage.key).length,
      description: stage.description,
      collapsed: collapsed.has(stage.key),
      onToggle: () => options.onToggle?.(stage.key),
    },
    draggable: false,
    selectable: false,
    connectable: false,
    initialWidth: CANVAS_COLUMN_WIDTH - 32,
    initialHeight: 30,
  }));

  const rows = new Map<WorkflowStageKey, number>();
  const nodes = canvas.nodes.filter((node) => !collapsed.has(node.stage)).map((node) => {
    const index = columns.get(node.stage) ?? 0;
    const row = rows.get(node.stage) ?? 0;
    rows.set(node.stage, row + 1);
    return {
      id: node.id,
      type: 'workflow',
      position: { x: columnX(index), y: CANVAS_HEADER_HEIGHT + row * CANVAS_ROW_HEIGHT },
      data: {
        label: node.title,
        subtitle: node.subtitle,
        status: node.status,
        tone: statusTone(node.status),
        kind: node.kind,
        entityId: node.entity_id,
        evidenceLine: discoveryEvidenceLine(node.metrics),
      },
      draggable: false,
      initialWidth: CANVAS_COLUMN_WIDTH - 32,
      initialHeight: 88,
    } satisfies Node<CanvasNodeData>;
  });

  return [...stages, ...nodes];
}

export function flowEdges(canvas: WorkflowCanvas): Edge[] {
  const known = new Set(canvas.nodes.map((node) => node.id));
  return canvas.edges
    .filter((edge) => known.has(edge.source) && known.has(edge.target))
    .map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      type: 'smoothstep',
      animated: false,
    }));
}

/** True while any node is mid-flight, which is what the canvas polls for. */
export function canvasIsLive(canvas: WorkflowCanvas | null): boolean {
  if (!canvas) return false;
  return canvas.nodes.some((node) => ['RUNNING', 'QUEUED', 'VERIFYING', 'WAITING'].includes(node.status));
}

export function stageSummary(canvas: WorkflowCanvas | null): string {
  if (!canvas || canvas.nodes.length === 0) return '';
  return canvas.stages
    .map((stage) => ({ title: stage.title, count: canvas.counts[stage.key] ?? 0 }))
    .filter((entry) => entry.count > 0)
    .map((entry) => `${entry.title} ${entry.count}`)
    .join(' · ');
}

/** The evidence line on a discovery card: raw → deduped, then what was tied to an action. */
export function discoveryEvidenceLine(metrics: DiscoveryMetrics | null | undefined): string {
  const evidence = metrics?.evidence;
  if (!evidence || !evidence.captured) return '';
  const parts = [
    `DOM ${evidence.dom_elements}→${evidence.dom_elements_deduped}`,
    `API ${evidence.requests}（关联 ${evidence.requests_associated}）`,
    `状态 ${evidence.page_states}`,
  ];
  if (evidence.locators_ambiguous > 0) parts.push(`歧义定位 ${evidence.locators_ambiguous}`);
  if (evidence.scenarios > 0) parts.push(`场景 ${evidence.scenarios}（缺口 ${evidence.candidate_gaps}）`);
  return parts.join(' · ');
}
