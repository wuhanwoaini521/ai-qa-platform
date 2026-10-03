import type { RuntimeSnapshot, RuntimeSpan } from '../../types/runtime';
import { liveSpan } from './runtimeModel.ts';
export function timelineSpans(snapshot: RuntimeSnapshot): RuntimeSpan[] {
  return [
    ...(snapshot.task ? [snapshot.task] : []),
    ...snapshot.steps,
    ...snapshot.runs,
    ...snapshot.executions,
    ...snapshot.browser_sessions,
    ...(snapshot.ai_invocations ?? []),
  ];
}
export function spanBounds(
  span: RuntimeSpan,
  now: number,
): { start: number; end: number } | null {
  const start = span.started_at ? Date.parse(span.started_at) : NaN;
  const end = span.finished_at
    ? Date.parse(span.finished_at)
    : liveSpan(span)
      ? now
      : NaN;
  return Number.isFinite(start) && Number.isFinite(end) && end >= start
    ? { start, end }
    : null;
}
export function timelineRange(spans: RuntimeSpan[], now: number) {
  const bounds = spans
    .map((span) => spanBounds(span, now))
    .filter((span): span is { start: number; end: number } => span !== null);
  if (!bounds.length) return null;
  const start = Math.min(...bounds.map((span) => span.start));
  const end = Math.max(...bounds.map((span) => span.end));
  return { start, end, duration: Math.max(30000, (end - start) * 1.15) };
}

/** Expand in powers of two so completed rows keep stable props between boundaries. */
export function timelineDomain(
  baseDuration: number,
  observedDuration: number,
  zoom: number,
) {
  const expansion = Math.max(
    0,
    Math.ceil(Math.log2(Math.max(1, observedDuration / baseDuration))),
  );
  return (baseDuration * 2 ** expansion) / zoom;
}
