import type { TestBrowserSession } from '../../types';
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
