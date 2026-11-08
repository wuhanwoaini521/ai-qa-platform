/**
 * Pure layout model for the requirement and editable plan canvas.
 *
 * The canvas visualises existing requirement data (criteria → scenario → actions → expected
 * outcomes). Layout stays independent from editing and execution; the plan editor persists its
 * separate `TestDesign` snapshot and Task Runtime compiles that snapshot at launch.
 */

export type FlowNodeKind = 'criterion' | 'scenario' | 'action' | 'assert';

export interface FlowNode {
  id: string;
  kind: FlowNodeKind;
  title: string;
  subtitle: string;
  /** 1-based position inside an action/assert chain; rendered as a badge, not translated text. */
  index?: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FlowEdge {
  id: string;
  from: string;
  to: string;
  kind: 'criterion' | 'sequence' | 'assert';
}

export interface FlowLayout {
  nodes: FlowNode[];
  edges: FlowEdge[];
  width: number;
  height: number;
}

export interface ScenarioLike {
  id: string;
  title: string;
  intent: string;
  priority: string;
  path_type: string;
  technique: string;
  coverage: { criterion_ids?: string[] };
  actions: string[];
  expected_outcomes: string[];
}

export interface CriterionLike {
  id: string;
  description: string;
}

const COLUMN_X = [40, 320, 620, 940] as const;
const NODE_WIDTH = [210, 240, 270, 260] as const;
const GAP_Y = 24;
const NODE_HEIGHT = 92;

function clip(text: string, limit: number): string {
  const clean = text.trim().replace(/\s+/g, ' ');
  return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean;
}

function columnHeight(count: number): number {
  return count > 0 ? count * NODE_HEIGHT + (count - 1) * GAP_Y : 0;
}

/**
 * Lay the scenario out in four columns: covered criteria, the scenario itself, its actions, and the
 * expected outcomes as assertion nodes. Positions are deterministic so screenshots and tests are stable.
 */
export function buildScenarioFlow(scenario: ScenarioLike, criteria: CriterionLike[]): FlowLayout {
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  const covered = new Set(scenario.coverage?.criterion_ids ?? []);
  const coveredCriteria = criteria.filter((criterion) => covered.has(criterion.id));

  const actions = (scenario.actions ?? []).map((action) => action.trim()).filter(Boolean);
  const outcomes = (scenario.expected_outcomes ?? []).map((outcome) => outcome.trim()).filter(Boolean);

  const actionsHeight = columnHeight(actions.length);
  const outcomesHeight = columnHeight(outcomes.length);
  const bodyHeight = Math.max(actionsHeight, outcomesHeight, NODE_HEIGHT);
  const scenarioY = Math.round((bodyHeight - NODE_HEIGHT) / 2);

  const criteriaStartY = Math.max(0, Math.round((bodyHeight - columnHeight(coveredCriteria.length)) / 2));
  coveredCriteria.forEach((criterion, index) => {
    const node: FlowNode = {
      id: `criterion:${criterion.id}`,
      kind: 'criterion',
      title: criterion.id,
      subtitle: clip(criterion.description, 60),
      x: COLUMN_X[0],
      y: criteriaStartY + index * (NODE_HEIGHT + GAP_Y),
      width: NODE_WIDTH[0],
      height: NODE_HEIGHT,
    };
    nodes.push(node);
    edges.push({ id: `edge:${node.id}->scenario`, from: node.id, to: 'scenario', kind: 'criterion' });
  });

  nodes.push({
    id: 'scenario',
    kind: 'scenario',
    title: clip(scenario.title, 42),
    subtitle: `${scenario.priority} · ${scenario.path_type} · ${scenario.technique}`,
    x: COLUMN_X[1],
    y: scenarioY,
    width: NODE_WIDTH[1],
    height: NODE_HEIGHT,
  });

  actions.forEach((action, index) => {
    const node: FlowNode = {
      id: `action:${index + 1}`,
      kind: 'action',
      title: clip(action, 80),
      subtitle: '',
      index: index + 1,
      x: COLUMN_X[2],
      y: index * (NODE_HEIGHT + GAP_Y),
      width: NODE_WIDTH[2],
      height: NODE_HEIGHT,
    };
    nodes.push(node);
    edges.push({
      id: `edge:scenario->${node.id}`,
      from: index === 0 ? 'scenario' : `action:${index}`,
      to: node.id,
      kind: 'sequence',
    });
  });

  outcomes.forEach((outcome, index) => {
    const node: FlowNode = {
      id: `assert:${index + 1}`,
      kind: 'assert',
      title: clip(outcome, 80),
      subtitle: '',
      index: index + 1,
      x: COLUMN_X[3],
      y: index * (NODE_HEIGHT + GAP_Y),
      width: NODE_WIDTH[3],
      height: NODE_HEIGHT,
    };
    nodes.push(node);
    const from = actions.length > 0 ? `action:${actions.length}` : 'scenario';
    edges.push({ id: `edge:${from}->${node.id}`, from, to: node.id, kind: 'assert' });
  });

  const width = COLUMN_X[3] + NODE_WIDTH[3] + 60;
  const height = Math.max(bodyHeight, columnHeight(coveredCriteria.length), NODE_HEIGHT) + 48;
  return { nodes, edges, width, height };
}

/** Orthogonal connector between two nodes, routing from the right edge to the left edge. */
export function edgePath(from: FlowNode, to: FlowNode): string {
  const startX = from.x + from.width;
  const startY = from.y + from.height / 2;
  const endX = to.x;
  const endY = to.y + to.height / 2;
  const midX = startX + Math.max(24, Math.round((endX - startX) / 2));
  return `M ${startX} ${startY} H ${midX} V ${endY} H ${endX}`;
}
