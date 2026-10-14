import test from 'node:test';
import assert from 'node:assert/strict';
import { browserEntries, formatBrowserTimestamp } from '../src/features/runtime/browserModel.ts';
test('browser telemetry replaces missing and invalid timestamps instead of showing Invalid Date', () => {
  for (const value of [undefined, null, '', 'not-a-date']) {
    assert.equal(formatBrowserTimestamp(value), '—');
  }
  const timestamp = '2026-10-13T12:30:00Z';
  assert.equal(formatBrowserTimestamp(timestamp), new Date(timestamp).toLocaleTimeString());
});

test('Browser telemetry uses actual sessions and bounded entries', () => {
  assert.equal(browserEntries([], 'network_logs').length, 0);
  const entries = browserEntries(
    [
      {
        browser_session_id: 'real',
        page_evidence: {
          network_logs: Array.from({ length: 150 }, (_, i) => ({
            url: `/real/${i}`,
            timestamp: null,
          })),
        },
      },
    ],
    'network_logs',
  );
  assert.equal(entries.length, 100);
  assert.equal(entries[0].entry.url, '/real/50');
  assert.equal(entries[0].session, 'real');
});
