import test from 'node:test';
import assert from 'node:assert/strict';

const { emptyDraft, validateDraft, toPayload, fromRecorderCall, slugTestName } = await import(
  '../src/features/api-cases/apiCase.ts'
);

const valid = () => ({ ...emptyDraft('test_health'), url: '/api/health' });

test('a minimal draft validates and defaults to a 200 assertion', () => {
  const draft = valid();
  assert.deepEqual(validateDraft(draft).errors, []);
  const payload = toPayload(draft);
  assert.equal(payload.url, '/api/health');
  assert.equal(payload.method, 'GET');
  assert.deepEqual(payload.assertions, [{ kind: 'status', expected: 200 }]);
});

test('missing url, bad status and bad JSON are rejected', () => {
  assert.ok(validateDraft(emptyDraft()).errors.includes('errorUrl'));
  const badStatus = { ...valid(), assertions: [{ id: 'a', kind: 'status', path: '', expected: '20' }] };
  assert.ok(validateDraft(badStatus).errors.includes('errorStatus'));
  const badJson = { ...valid(), body: '{not json', useJsonBody: true };
  assert.ok(validateDraft(badJson).errors.includes('errorJsonBody'));
  const noPath = { ...valid(), assertions: [{ id: 'a', kind: 'json_path', path: ' ', expected: '1' }] };
  assert.ok(validateDraft(noPath).errors.includes('errorJsonPath'));
});

test('payload converts status, JSON paths and JSON bodies', () => {
  const draft = {
    ...valid(),
    method: 'POST',
    useJsonBody: true,
    body: '{"sku": "tee"}',
    headers: [{ id: 'h', name: ' content-type ', value: 'application/json' }, { id: 'h2', name: ' ', value: 'x' }],
    assertions: [
      { id: 'a1', kind: 'status', path: '', expected: '201' },
      { id: 'a2', kind: 'json_path', path: 'data.id', expected: '7' },
    ],
  };
  const payload = toPayload(draft);
  assert.deepEqual(payload.headers, [{ name: 'content-type', value: 'application/json' }]);
  assert.deepEqual(payload.json_body, { sku: 'tee' });
  assert.deepEqual(payload.assertions, [
    { kind: 'status', expected: 201 },
    { kind: 'json_path', path: 'data.id', expected: 7 },
  ]);
});

test('recorder calls prefill method, path, status and headers', () => {
  const draft = fromRecorderCall({
    id: 'c1',
    method: 'POST',
    url: 'http://127.0.0.1:8099/api/orders?x=1',
    status: 201,
    failed: false,
    request_headers: { accept: 'application/json', authorization: '[REDACTED]' },
    request_body: '{"sku":"tee"}',
    response_content_type: 'application/json',
  });
  assert.equal(draft.method, 'POST');
  assert.equal(draft.url, '/api/orders?x=1');
  assert.equal(draft.useJsonBody, true);
  assert.equal(draft.assertions[0].expected, '201');
  assert.ok(draft.headers.some((row) => row.name === 'authorization'));
  assert.equal(draft.test_name.startsWith('test_post_api_orders'), true);
});

test('api test names stay ascii and prefixed', () => {
  assert.equal(slugTestName('GET /api/health'), 'test_get_api_health');
  assert.equal(slugTestName('接口 检查'), 'test_api_case');
});
