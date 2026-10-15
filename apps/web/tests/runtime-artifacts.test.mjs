import test from 'node:test';
import assert from 'node:assert/strict';
import {
  artifactPreviewKind,
  artifactFilename,
  safeArtifactUrl,
} from '../src/features/runtime/artifactModel.ts';
test('Artifact previews reflect actual type and safe external schemes', () => {
  assert.equal(
    artifactPreviewKind({ name: 'actual.png', content_type: 'image/png' }),
    'image',
  );
  assert.equal(artifactPreviewKind({ name: 'report.html' }), 'report');
  assert.equal(artifactPreviewKind({ name: 'generated.py' }), 'text');
  assert.equal(artifactPreviewKind({ name: 'test_product_detail.zip' }), 'trace');
  assert.equal(artifactPreviewKind({ name: 'trace.data', type: 'PLAYWRIGHT_TRACE' }), 'trace');
  assert.equal(artifactPreviewKind({ name: 'unknown.bin' }), null);
  assert.equal(safeArtifactUrl('javascript:alert(1)'), null);
  assert.equal(safeArtifactUrl('https://user:pass@host/report'), null);
  assert.equal(
    safeArtifactUrl('https://example.com/report'),
    'https://example.com/report',
  );
});
test('Downloads use filenames and cannot carry local paths or control characters', () => {
  assert.equal(artifactFilename('C:\\secret\\test.py'), 'test.py');
  assert.equal(artifactFilename('../report\n.html'), 'report_.html');
});
