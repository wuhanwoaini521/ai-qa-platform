import type { AITraceEvent } from '../../types';
export function appendProgress(events: AITraceEvent[], event: AITraceEvent) {
  if (
    ['model.delta', 'operation.result'].includes(event.type) ||
    events.some((item) => item.event_id === event.event_id)
  )
    return events;
  const { content: _content, ...progress } = event;
  return [...events, progress].slice(-500);
}
