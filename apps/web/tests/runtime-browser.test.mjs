import test from 'node:test';
import assert from 'node:assert/strict';
import { browserEntries } from '../src/features/runtime/browserModel.ts';
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
