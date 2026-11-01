import test from 'node:test';
import assert from 'node:assert/strict';

const { emptyDraft, validateDraft, toPayload, fromRecorderCall, slugTestName, fromHarDocument, fromOpenApiDocument } = await import(
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

test('HAR import keeps API traffic only and maps request details', () => {
  const har = {
    log: {
      entries: [
        {
          _resourceType: 'xhr',
          request: {
            method: 'GET',
            url: 'http://127.0.0.1:8099/api/info?x=1',
            headers: [{ name: 'Accept', value: 'application/json' }],
          },
          response: { status: 200, content: { mimeType: 'application/json' } },
        },
        { ...{}, _resourceType: 'xhr', request: { method: 'GET', url: 'http://127.0.0.1:8099/api/info?x=1' }, response: { status: 200 } },
        { _resourceType: 'script', request: { method: 'GET', url: 'http://127.0.0.1:8099/app.js' }, response: { status: 200, content: { mimeType: 'text/javascript' } } },
        { _resourceType: 'fetch', request: { method: 'POST', url: 'http://127.0.0.1:8099/api/orders', headers: [], postData: { text: '{"sku":"tee"}' } }, response: { status: 201, content: { mimeType: 'application/json' } } },
      ],
    },
  };
  const calls = fromHarDocument(har);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, 'http://127.0.0.1:8099/api/info?x=1');
  assert.equal(calls[0].request_headers.accept, 'application/json');
  assert.equal(calls[1].method, 'POST');
  assert.equal(calls[1].request_body, '{"sku":"tee"}');
  assert.equal(calls[1].status, 201);
});

test('HAR import rejects a document without entries', () => {
  assert.throws(() => fromHarDocument(null), /invalid-har/);
  assert.throws(() => fromHarDocument({ log: {} }), /invalid-har/);
});

test('OpenAPI import lists operations with a preferred success status', () => {
  const operations = fromOpenApiDocument({
    paths: {
      '/api/orders': {
        get: { summary: 'List orders', responses: { '200': {}, '500': {} } },
        post: { operationId: 'createOrder', responses: { '201': {}, '400': {} } },
      },
      '/api/health': { parameters: [], get: { responses: { default: {} } } },
    },
  });
  assert.deepEqual(
    operations.map((item) => [item.method, item.path, item.expectedStatus]),
    [
      ['GET', '/api/orders', '200'],
      ['POST', '/api/orders', '201'],
      ['GET', '/api/health', '200'],
    ],
  );
  assert.equal(operations[1].summary, 'createOrder');
});

test('OpenAPI import rejects a document without paths', () => {
  assert.throws(() => fromOpenApiDocument({}), /invalid-openapi/);
});

test('OpenAPI import extracts a simplified response schema', () => {
  const operations = fromOpenApiDocument({
    paths: {
      '/api/info': {
        get: {
          responses: {
            200: {
              content: {
                'application/json': {
                  schema: {
                    type: 'object',
                    description: 'should be dropped',
                    required: ['ok', 'service'],
                    properties: {
                      ok: { type: 'boolean' },
                      service: { type: 'string' },
                      count: { type: 'integer' },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
  });
  assert.deepEqual(operations[0].responseSchema, {
    type: 'object',
    required: ['ok', 'service'],
    properties: { ok: { type: 'boolean' }, service: { type: 'string' }, count: { type: 'integer' } },
  });
});

test('contract assertions serialize and validate', () => {
  const draft = {
    ...valid(),
    assertions: [{ id: 'a', kind: 'json_contract', path: '', expected: '{"type":"object","required":["ok"]}' }],
  };
  assert.deepEqual(validateDraft(draft).errors, []);
  assert.deepEqual(toPayload(draft).assertions, [
    { kind: 'json_contract', expected: { type: 'object', required: ['ok'] } },
  ]);

  const broken = { ...draft, assertions: [{ id: 'a', kind: 'json_contract', path: '', expected: '{oops' }] };
  assert.ok(validateDraft(broken).errors.includes('errorContractSchema'));
});
