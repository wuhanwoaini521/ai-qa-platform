import type { KnowledgeNode, ProjectKnowledge } from "./types";

export const KIND_ORDER = [
  "project",
  "requirement",
  "criteria",
  "rules",
  "risks",
  "flow",
  "scenarios",
  "design",
  "case",
  "automation",
  "run",
  "failure",
  "patch",
  "evidence",
];
export function visibleGraph(
  graph: ProjectKnowledge,
  query: string,
  kind: string,
  collapsed: Set<string>,
) {
  const hidden = new Set<string>();
  const descendants = [...collapsed];
  while (descendants.length) {
    const parent = descendants.pop()!;
    for (const edge of graph.edges) {
      if (
        edge.source === parent &&
        ["contains", "designed_as", "automated_by", "evidenced_by"].includes(
          edge.relation,
        ) &&
        !hidden.has(edge.target)
      ) {
        hidden.add(edge.target);
        descendants.push(edge.target);
      }
    }
  }
  const text = query.toLocaleLowerCase().trim();
  const nodes = graph.nodes.filter(
    (node) =>
      !hidden.has(node.id) &&
      (!kind || kind === node.kind) &&
      (!text ||
        `${node.label} ${node.summary} ${node.status}`
          .toLocaleLowerCase()
          .includes(text)),
  );
  const selected = new Set(nodes.map((node) => node.id));
  return {
    nodes,
    edges: graph.edges.filter(
      (edge) => selected.has(edge.source) && selected.has(edge.target),
    ),
  };
}
export function focusedGraph(
  graph: Pick<ProjectKnowledge, "nodes" | "edges">,
  focus: string,
) {
  const edges = graph.edges.filter(
    (edge) => edge.source === focus || edge.target === focus,
  );
  const ids = new Set([
    focus,
    ...edges.flatMap((edge) => [edge.source, edge.target]),
  ]);
  return { nodes: graph.nodes.filter((node) => ids.has(node.id)), edges };
}

export const GRAPH_NODE_WIDTH = 240;
export const GRAPH_NODE_HEIGHT = 108;

export function defaultGraphFocus(
  graph: Pick<ProjectKnowledge, "nodes" | "edges">,
  mode: string,
  initialNode?: string,
) {
  const requested = graph.nodes.find(
    (node) =>
      initialNode &&
      (node.id === initialNode || node.id.endsWith(`:${initialNode}`)),
  );
  if (requested) return requested;
  const candidates = graph.nodes.filter(
    (node) => node.kind === (mode === "knowledge" ? "case" : "scenarios"),
  );
  const automated =
    mode === "knowledge"
      ? candidates.filter((node) =>
          graph.edges.some(
            (edge) =>
              edge.source === node.id && edge.relation === "automated_by",
          ),
        )
      : [];
  const degree = (id: string) =>
    graph.edges.filter((edge) => edge.source === id || edge.target === id)
      .length;
  const connected = (automated.length ? automated : candidates).filter(
    (node) => degree(node.id) > 1,
  );
  return (
    [...(connected.length ? connected : candidates)].sort(
      (a, b) =>
        degree(a.id) - degree(b.id) ||
        a.label.localeCompare(b.label, undefined, { numeric: true }),
    )[0] ?? graph.nodes[0]
  );
}

export function fitGraphViewport(
  width: number,
  height: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  const scale = Math.max(
    0.01,
    Math.min(1, (viewportWidth - 48) / width, (viewportHeight - 48) / height),
  );
  return {
    scale,
    offset: {
      x: (viewportWidth - width * scale) / 2,
      y: (viewportHeight - height * scale) / 2,
    },
  };
}

export function layoutGraph(
  nodes: KnowledgeNode[],
  edges: ProjectKnowledge["edges"] = [],
  focus?: string,
) {
  const kinds = KIND_ORDER.filter((kind) =>
    nodes.some((node) => node.kind === kind),
  );
  const positions = new Map<string, { x: number; y: number }>();
  const columns = focus
    ? [
        nodes.filter(
          (node) =>
            node.id !== focus &&
            edges.some(
              (edge) => edge.target === focus && edge.source === node.id,
            ),
        ),
        nodes.filter((node) => node.id === focus),
        nodes.filter(
          (node) =>
            node.id !== focus &&
            !edges.some(
              (edge) => edge.target === focus && edge.source === node.id,
            ),
        ),
      ].filter((column) => column.length)
    : kinds.map((kind) => nodes.filter((node) => node.kind === kind));
  const rows = Math.max(1, ...columns.map((column) => column.length));
  columns.forEach((items, column) =>
    items.forEach((node, row) =>
      positions.set(node.id, {
        x: 24 + column * 300,
        y: 30 + (row + (rows - items.length) / 2) * 132,
      }),
    ),
  );
  return {
    positions,
    width: Math.max(GRAPH_NODE_WIDTH + 48, columns.length * 300 - 12),
    height: rows * 132 + 36,
  };
}
