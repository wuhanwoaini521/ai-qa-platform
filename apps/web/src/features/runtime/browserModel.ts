import type { TestBrowserSession } from '../../types';

export function formatBrowserTimestamp(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString();
}
export function browserEntries(
  sessions: TestBrowserSession[],
  channel: 'recent_steps' | 'network_logs' | 'console_logs',
) {
  return sessions
    .flatMap((session) =>
      (Array.isArray(session.page_evidence?.[channel])
        ? session.page_evidence[channel]
        : []
      ).map((entry: Record<string, unknown>) => ({
        session: session.browser_session_id,
        entry,
      })),
    )
    .slice(-100);
}
