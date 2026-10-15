import test from "node:test";
import assert from "node:assert/strict";
import {
  visibleGraph,
  layoutGraph,
  focusedGraph,
  fitGraphViewport,
  GRAPH_NODE_WIDTH,
  GRAPH_NODE_HEIGHT,
  defaultGraphFocus,
} from "../src/features/lifecycle/graphModel.ts";
import {
  rememberEntity,
  recallEntity,
} from "../src/features/lifecycle/contextMemory.ts";

const nodes = [
  {
    id: "req",
    kind: "requirement",
    label: "REQ-001",
    summary: "Purchase",
    status: "READY",
  },
  {
    id: "ac",
    kind: "criteria",
    label: "AC-004",
    summary: "Cart amount",
    status: "",
  },
  {
    id: "case",
    kind: "case",
    label: "TC-004",
    summary: "Add to cart",
    status: "PASSED",
  },
];
const graph = {
  nodes,
  edges: [
    { source: "req", target: "ac", relation: "contains" },
    { source: "ac", target: "case", relation: "covered_by" },
  ],
};

test("search and kind filtering retain only edges between visible nodes", () => {
  const value = visibleGraph(graph, "cart", "", new Set());
  assert.deepEqual(
    value.nodes.map((n) => n.id),
    ["ac", "case"],
  );
  assert.equal(value.edges.length, 1);
  assert.equal(visibleGraph(graph, "", "case", new Set()).edges.length, 0);
});
test("branch collapsing hides owned children without hiding shared case references", () => {
  const value = visibleGraph(graph, "", "", new Set(["req"]));
  assert.deepEqual(
    value.nodes.map((n) => n.id),
    ["req", "case"],
  );
  assert.equal(value.edges.length, 0);
});
test("layout gives visible nodes distinct positions", () => {
  const layout = layoutGraph(nodes);
  assert.equal(
    new Set([...layout.positions.values()].map((p) => `${p.x},${p.y}`)).size,
    3,
  );
});
test("focused view retains only direct relationships and leaves the complete graph intact", () => {
  const full = {
    nodes: [...nodes, { id: "old-run", kind: "run", label: "Historical run" }],
    edges: [
      ...graph.edges,
      { source: "case", target: "old-run", relation: "executed_by" },
    ],
  };
  const value = focusedGraph(full, "ac");
  assert.deepEqual(
    value.nodes.map((n) => n.id),
    ["req", "ac", "case"],
  );
  assert.equal(value.edges.length, 2);
  assert.equal(full.nodes.length, 4);
  assert.equal(full.edges.length, 3);
  assert.deepEqual(
    focusedGraph(full, "old-run").nodes.map((n) => n.id),
    ["case", "old-run"],
  );
});

test("default focus selects a connected, readable business object while respecting deep links", () => {
  const value = {
    nodes: [
      { id: "broad", kind: "scenarios", label: "SCN-001" },
      { id: "small", kind: "scenarios", label: "SCN-002" },
      { id: "empty", kind: "scenarios", label: "SCN-003" },
      ...nodes,
    ],
    edges: [
      { source: "req", target: "broad", relation: "contains" },
      { source: "broad", target: "ac", relation: "covers" },
      { source: "broad", target: "case", relation: "covers" },
      { source: "req", target: "small", relation: "contains" },
      { source: "small", target: "ac", relation: "covers" },
    ],
  };
  assert.equal(defaultGraphFocus(value, "mind").id, "small");
  assert.equal(defaultGraphFocus(value, "mind", "broad").id, "broad");
  const automated = {
    nodes: [{ id: "unbound", kind: "case", label: "TC-001" }, ...nodes],
    edges: [
      ...graph.edges,
      { source: "case", target: "binding", relation: "automated_by" },
    ],
  };
  assert.equal(defaultGraphFocus(automated, "knowledge").id, "case");
});
test("focused layout places actual upstream and downstream around the selected entity", () => {
  const layout = layoutGraph(nodes, graph.edges, "ac");
  assert.ok(layout.positions.get("req").x < layout.positions.get("ac").x);
  assert.ok(layout.positions.get("ac").x < layout.positions.get("case").x);
  for (const position of layout.positions.values()) {
    assert.ok(position.x >= 0 && position.x + GRAPH_NODE_WIDTH <= layout.width);
    assert.ok(
      position.y >= 0 && position.y + GRAPH_NODE_HEIGHT <= layout.height,
    );
  }
});
test("fit centers the actual graph at desktop and narrow widths, including large histories", () => {
  for (const [width, height, vw, vh] of [
    [888, 696, 900, 520],
    [288, 168, 900, 520],
    [4200, 18000, 800, 520],
    [888, 696, 360, 440],
  ]) {
    const fitted = fitGraphViewport(width, height, vw, vh);
    assert.ok(fitted.scale > 0 && fitted.scale <= 1);
    assert.ok(width * fitted.scale <= vw - 48 + 1e-8);
    assert.ok(height * fitted.scale <= vh - 48 + 1e-8);
    assert.equal(fitted.offset.x, (vw - width * fitted.scale) / 2);
    assert.equal(fitted.offset.y, (vh - height * fitted.scale) / 2);
  }
});
test("remembered entities are scoped by project and unavailable storage is safe", () => {
  const values = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, v),
  };
  rememberEntity("one", "case", "TC-004");
  rememberEntity("two", "case", "TC-009");
  assert.equal(recallEntity("one", "case"), "TC-004");
  assert.equal(recallEntity("two", "case"), "TC-009");
  delete globalThis.sessionStorage;
  assert.equal(recallEntity("one", "case"), null);
});
