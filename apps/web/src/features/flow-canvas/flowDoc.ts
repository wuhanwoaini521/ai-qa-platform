/**
 * Editable flow document model.
 *
 * Same node kinds the backend compiles (`FlowDocument` in flow_compiler.py). Keeping validation
 * here gives instant feedback; the server stays authoritative when compiling.
 */

export type FlowKind =
  | 'navigate'
  | 'click'
  | 'fill'
  | 'assert_text'
  | 'assert_visible'
  | 'wait'
  | 'condition';

export type LocatorKind = 'css' | 'test_id' | 'role' | 'label' | 'placeholder' | 'id' | 'name' | 'text';

export interface FlowNode {
  id: string;
  kind: FlowKind;
  description: string;
  url: string;
  locator_kind: LocatorKind;
  locator_value: string;
  locator_name: string;
  value: string;
  env_var: string;
  condition_kind: 'css' | 'text' | 'test_id';
  condition_value: string;
  /** Acceptance criteria this assertion verifies; empty until the author binds them. */
  criterion_ids: string[];
  then: FlowNode[];
  else_nodes: FlowNode[];
}

export interface FlowDoc {
  version: 1;
  test_name: string;
  nodes: FlowNode[];
}

export type FlowBranch = 'then' | 'else_nodes';

export const MAX_DEPTH = 5;

let nodeCounter = 0;

export function nextNodeId(prefix = 'n'): string {
  nodeCounter += 1;
  return `${prefix}${Date.now().toString(36)}${nodeCounter}`;
}

export const KIND_LABEL: Record<FlowKind, string> = {
  navigate: 'kindNavigate',
  click: 'kindClick',
  fill: 'kindFill',
  assert_text: 'kindAssertText',
  assert_visible: 'kindAssertVisible',
  wait: 'kindWait',
  condition: 'kindCondition',
};

export function emptyNode(kind: FlowKind): FlowNode {
  return {
    id: nextNodeId(kind === 'condition' ? 'c' : 'n'),
    kind,
    description: '',
    url: '',
    locator_kind: 'css',
    locator_value: '',
    locator_name: '',
    value: kind === 'wait' ? '1000' : '',
    env_var: '',
    condition_kind: 'css',
    condition_value: '',
    criterion_ids: [],
    then: [],
    else_nodes: [],
  };
}

export function emptyFlow(testName = 'flow_canvas_case', startUrl = ''): FlowDoc {
  const navigate = emptyNode('navigate');
  navigate.url = startUrl;
  return { version: 1, test_name: testName, nodes: [navigate] };
}

export function countNodes(nodes: FlowNode[]): number {
  return nodes.reduce((total, node) => total + 1 + countNodes(node.then) + countNodes(node.else_nodes), 0);
}

export function maxDepth(nodes: FlowNode[], depth = 1): number {
  return nodes.reduce(
    (deepest, node) => Math.max(deepest, maxDepth(node.then, depth + 1), maxDepth(node.else_nodes, depth + 1)),
    nodes.length ? depth : 0,
  );
}

function mapList(
  nodes: FlowNode[],
  parentId: string | null,
  branch: FlowBranch,
  transform: (list: FlowNode[]) => FlowNode[],
): FlowNode[] {
  if (parentId === null) return transform(nodes);
  return nodes.map((node) => {
    if (node.id === parentId) {
      return { ...node, [branch]: transform(node[branch]) };
    }
    return {
      ...node,
      then: mapList(node.then, parentId, branch, transform),
      else_nodes: mapList(node.else_nodes, parentId, branch, transform),
    };
  });
}

export function insertNode(flow: FlowDoc, parentId: string | null, branch: FlowBranch, node: FlowNode, index?: number): FlowDoc {
  const nodes = mapList(flow.nodes, parentId, branch, (list) => {
    const next = [...list];
    next.splice(index === undefined ? next.length : Math.min(index, next.length), 0, node);
    return next;
  });
  return { ...flow, nodes };
}

export function updateNode(flow: FlowDoc, id: string, patch: Partial<FlowNode>): FlowDoc {
  const walk = (nodes: FlowNode[]): FlowNode[] =>
    nodes.map((node) =>
      node.id === id
        ? { ...node, ...patch }
        : { ...node, then: walk(node.then), else_nodes: walk(node.else_nodes) },
    );
  return { ...flow, nodes: walk(flow.nodes) };
}

export function removeNode(flow: FlowDoc, id: string): FlowDoc {
  const walk = (nodes: FlowNode[]): FlowNode[] =>
    nodes
      .filter((node) => node.id !== id)
      .map((node) => ({ ...node, then: walk(node.then), else_nodes: walk(node.else_nodes) }));
  return { ...flow, nodes: walk(flow.nodes) };
}

export function moveNode(
  flow: FlowDoc,
  parentId: string | null,
  branch: FlowBranch,
  from: number,
  to: number,
): FlowDoc {
  const nodes = mapList(flow.nodes, parentId, branch, (list) => {
    if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
    const next = [...list];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    return next;
  });
  return { ...flow, nodes };
}

export function findParent(nodes: FlowNode[], id: string, parentId: string | null = null, branch: FlowBranch = 'then'): { parentId: string | null; branch: FlowBranch } | null {
  for (const node of nodes) {
    if (node.id === id) return { parentId, branch };
    const found = findParent(node.then, id, node.id, 'then') ?? findParent(node.else_nodes, id, node.id, 'else_nodes');
    if (found) return found;
  }
  return null;
}

export interface FlowValidation {
  errors: string[];
  warnings: string[];
}

export function validateFlow(flow: FlowDoc): FlowValidation {
  const errors: string[] = [];
  const warnings: string[] = [];
  const ids: string[] = [];

  if (flow.nodes.length === 0) errors.push('errorEmpty');
  if (flow.nodes[0] && flow.nodes[0].kind !== 'navigate') errors.push('errorStartNavigate');

  const walk = (nodes: FlowNode[]) => {
    for (const node of nodes) {
      ids.push(node.id);
      const label = node.description || node.kind;
      if (node.kind === 'navigate' && !node.url.trim()) errors.push(`errorUrlRequired|${label}`);
      if (['click', 'fill', 'assert_text', 'assert_visible'].includes(node.kind) && !node.locator_value.trim()) {
        errors.push(`errorLocatorRequired|${label}`);
      }
      if (node.kind === 'fill' && !node.value.trim() && !node.env_var.trim()) {
        errors.push(`errorValueRequired|${label}`);
      }
      if (node.kind === 'fill' && node.value.trim() && node.env_var.trim()) {
        errors.push(`errorValueOrEnv|${label}`);
      }
      if (node.kind === 'condition' && !node.condition_value.trim()) errors.push(`errorConditionRequired|${label}`);
      if (node.kind !== 'condition' && (node.then.length || node.else_nodes.length)) {
        errors.push(`errorBranchesOnlyOnCondition|${label}`);
      }
      if (node.kind === 'condition' && node.then.length === 0 && node.else_nodes.length === 0) {
        warnings.push(`warnEmptyBranches|${label}`);
      }
      if ((node.kind === 'assert_text' || node.kind === 'assert_visible') && node.criterion_ids.length === 0) {
        warnings.push(`warnCriterionMissing|${label}`);
      }
      walk(node.then);
      walk(node.else_nodes);
    }
  };
  walk(flow.nodes);

  if (new Set(ids).size !== ids.length) errors.push('errorDuplicateIds');
  if (maxDepth(flow.nodes) > MAX_DEPTH) errors.push('errorDepth');
  return { errors, warnings };
}

/** Seed an editable flow from the read-only scenario model (P0 data). */
export function toggleCriterion(node: FlowNode, criterionId: string): FlowNode {
  const selected = node.criterion_ids.includes(criterionId)
    ? node.criterion_ids.filter((item) => item !== criterionId)
    : [...node.criterion_ids, criterionId];
  return { ...node, criterion_ids: selected };
}

export function flowFromScenario(
  scenario: { title: string; actions: string[]; expected_outcomes: string[] },
  startUrl: string,
): FlowDoc {
  const flow = emptyFlow(slugTestName(scenario.title), startUrl);
  for (const action of scenario.actions) {
    const node = emptyNode('click');
    node.description = action;
    node.locator_value = '';
    flow.nodes.push(node);
  }
  for (const outcome of scenario.expected_outcomes) {
    const node = emptyNode('assert_visible');
    node.description = outcome;
    flow.nodes.push(node);
  }
  return flow;
}

export function slugTestName(title: string): string {
  // Keep file names ASCII: a Chinese requirement title would otherwise produce a non-ASCII module path.
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return `test_${slug || 'flow_canvas_case'}`.slice(0, 60);
}
