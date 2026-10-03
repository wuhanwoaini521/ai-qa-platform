import type { RuntimeSnapshot } from '../../types/runtime';

/** Preserve unchanged records so an event does not rerender every node and lane. */
export function reconcileSnapshot(
  previous: RuntimeSnapshot | null,
  incoming: RuntimeSnapshot,
): RuntimeSnapshot {
  if (
    !previous ||
    previous.id !== incoming.id ||
    previous.kind !== incoming.kind
  )
    return incoming;
  const result = { ...incoming };
  for (const key of Object.keys(incoming) as (keyof RuntimeSnapshot)[]) {
    const next = incoming[key],
      old = previous[key];
    let value: unknown = next;
    if (Array.isArray(next) && Array.isArray(old)) {
      const records = new Map(old.map((item) => [item.id, item]));
      const items = next.map((item) => {
        const existing = records.get(item.id);
        return existing && JSON.stringify(existing) === JSON.stringify(item)
          ? existing
          : item;
      });
      value =
        items.length === old.length &&
        items.every((item, index) => item === old[index])
          ? old
          : items;
    } else if (
      typeof next === 'object' &&
      next !== null &&
      JSON.stringify(next) === JSON.stringify(old)
    )
      value = old;
    Object.assign(result, { [key]: value });
  }
  return (Object.keys(result) as (keyof RuntimeSnapshot)[]).every(
    (key) => result[key] === previous[key],
  )
    ? previous
    : result;
}
