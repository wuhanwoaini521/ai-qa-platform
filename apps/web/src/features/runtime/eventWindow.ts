export const EVENT_ROW_HEIGHT = 32;
export function eventWindow(total: number, scrollTop: number, height: number) {
  const start = Math.max(
    0,
    Math.min(total, Math.floor(Math.max(0, scrollTop) / EVENT_ROW_HEIGHT) - 4),
  );
  const end = Math.min(
    total,
    start + Math.ceil(Math.max(0, height) / EVENT_ROW_HEIGHT) + 8,
  );
  return { start, end, height: total * EVENT_ROW_HEIGHT };
}
export function nearEventTail(
  scrollTop: number,
  clientHeight: number,
  scrollHeight: number,
) {
  return scrollHeight - scrollTop - clientHeight < 40;
}
