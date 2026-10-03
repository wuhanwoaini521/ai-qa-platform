import type { RuntimeStep } from '../../types/runtime';

type GraphStep = Pick<RuntimeStep, 'id' | 'key' | 'dependencies'>;
export type FlowDirection = 'horizontal' | 'vertical';
export const FLOW_NODE_WIDTH = 272;
export const FLOW_NODE_HEIGHT = 184;
export function graphStructure(steps: GraphStep[]) {
  return JSON.stringify(
    steps
      .map((step) => [step.id, step.key, [...step.dependencies].sort()])
      .sort((a, b) => String(a[0]).localeCompare(String(b[0]))),
  );
}
/** Stable dependency layering. Unknown dependencies and cycles remain visible as diagnostics. */
export function layoutDAG(
  steps: GraphStep[],
  direction: FlowDirection = 'horizontal',
) {
  const byKey = new Map(steps.map((step) => [step.key, step]));
  const levels = new Map<string, number>();
  const edges: { source: string; target: string }[] = [];
  const unknown: string[] = [];
  const ordered = [...steps].sort(
    (a, b) => a.key.localeCompare(b.key) || a.id.localeCompare(b.id),
  );
  for (const step of ordered)
    for (const key of new Set(step.dependencies)) {
      const dependency = byKey.get(key);
      if (dependency) edges.push({ source: dependency.id, target: step.id });
      else unknown.push(`${step.key}: ${key}`);
    }
  let pending = ordered;
  while (pending.length) {
    const ready = pending.filter((step) =>
      step.dependencies.every(
        (key) => !byKey.has(key) || levels.has(byKey.get(key)!.id),
      ),
    );
    if (!ready.length) break;
    for (const step of ready)
      levels.set(
        step.id,
        Math.max(
          0,
          ...step.dependencies
            .filter((key) => byKey.has(key))
            .map((key) => levels.get(byKey.get(key)!.id)! + 1),
        ),
      );
    const ids = new Set(ready.map((step) => step.id));
    pending = pending.filter((step) => !ids.has(step.id));
  }
  const cycle = pending.map((step) => step.id);
  const last = Math.max(0, ...levels.values()) + 1;
  for (const step of pending) levels.set(step.id, last);
  const positions = new Map<string, { x: number; y: number }>();
  const rows = new Map<number, number>();
  for (const step of ordered) {
    const level = levels.get(step.id)!;
    const row = rows.get(level) ?? 0;
    rows.set(level, row + 1);
    positions.set(
      step.id,
      direction === 'horizontal'
        ? {
            x: 24 + level * (FLOW_NODE_WIDTH + 64),
            y: 24 + row * (FLOW_NODE_HEIGHT + 56),
          }
        : {
            x: 24 + row * (FLOW_NODE_WIDTH + 64),
            y: 24 + level * (FLOW_NODE_HEIGHT + 56),
          },
    );
  }
  return {
    positions,
    edges,
    cycle,
    unknown,
    order: [...ordered]
      .sort(
        (a, b) =>
          levels.get(a.id)! - levels.get(b.id)! ||
          a.key.localeCompare(b.key) ||
          a.id.localeCompare(b.id),
      )
      .map((step) => step.id),
    width: Math.max(
      FLOW_NODE_WIDTH + 48,
      ...[...positions.values()].map((p) => p.x + FLOW_NODE_WIDTH + 24),
    ),
    height: Math.max(
      FLOW_NODE_HEIGHT + 48,
      ...[...positions.values()].map((p) => p.y + FLOW_NODE_HEIGHT + 24),
    ),
  };
}
