import type { KnowledgeNode, ProjectKnowledge } from './types';

export const KIND_ORDER = ['project', 'requirement', 'criteria', 'rules', 'risks', 'flow', 'scenarios', 'design', 'case', 'automation', 'run', 'failure', 'patch', 'evidence'];
export function visibleGraph(graph: ProjectKnowledge, query: string, kind: string, collapsed: Set<string>) {
  const hidden = new Set<string>();
  const descendants = [...collapsed];
  while (descendants.length) {
    const parent = descendants.pop()!;
    for (const edge of graph.edges) {
      if (edge.source === parent && ['contains', 'designed_as', 'automated_by', 'evidenced_by'].includes(edge.relation) && !hidden.has(edge.target)) {
        hidden.add(edge.target); descendants.push(edge.target);
      }
    }
  }
  const text = query.toLocaleLowerCase().trim();
  const nodes = graph.nodes.filter(node => !hidden.has(node.id) && (!kind || kind === node.kind)
    && (!text || `${node.label} ${node.summary} ${node.status}`.toLocaleLowerCase().includes(text)));
  const selected = new Set(nodes.map(node => node.id));
  return {nodes, edges: graph.edges.filter(edge => selected.has(edge.source) && selected.has(edge.target))};
}
export function layoutGraph(nodes: KnowledgeNode[]) {
  const kinds = KIND_ORDER.filter(kind => nodes.some(node => node.kind === kind));
  const positions = new Map<string, {x: number; y: number}>();
  kinds.forEach((kind, column) => nodes.filter(node => node.kind === kind).forEach((node, row) => positions.set(node.id, {x: 30 + column * 250, y: 50 + row * 112})));
  return {positions, width: Math.max(800, kinds.length * 250 + 30), height: Math.max(350, ...kinds.map(kind => 80 + nodes.filter(node => node.kind === kind).length * 112))};
}
