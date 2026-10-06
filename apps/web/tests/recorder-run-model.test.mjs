import test from 'node:test';
import assert from 'node:assert/strict';

const { recorderRunConfigFields, recorderRunIdempotencyKey, clearRecorderRunIdempotencyKey } = await import('../src/pages/recorderRunModel.ts');

test('recorder-created runs use the selected workspace environment, browser, and worker count', () => {
  assert.deepEqual(recorderRunConfigFields({
    environment: 'staging',
    region: 'JP',
    browser: 'chromium',
    workers: 2,
  }), {
    browser: 'chromium',
    environment: { QA_ENVIRONMENT: 'staging', QA_REGION: 'JP' },
    parallel_workers: 2,
  });
});

test('standalone recorder runs preserve API defaults when no workspace config is supplied', () => {
  assert.deepEqual(recorderRunConfigFields(), {});
});

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test('a retry with the same recorder Run intent reuses its key after a lost response', () => {
  const storage = memoryStorage();
  let next = 0;
  const createKey = () => `run-key-${++next}`;
  const intent = { project_id: 'project-1', workspace_id: 'project-1', nodeids: ['tests/test_search.py::test_search'] };

  const first = recorderRunIdempotencyKey('project-1:test_search', intent, storage, createKey);
  const retry = recorderRunIdempotencyKey('project-1:test_search', intent, storage, createKey);

  assert.equal(first, 'run-key-1');
  assert.equal(retry, first);
  assert.equal(next, 1);
});

test('a changed recorder Run intent gets a new key, and success clearing starts a fresh Run', () => {
  const storage = memoryStorage();
  let next = 0;
  const createKey = () => `run-key-${++next}`;
  const scope = 'project-1:test_search';
  const intent = { project_id: 'project-1', nodeids: ['tests/test_search.py::test_search'] };

  const first = recorderRunIdempotencyKey(scope, intent, storage, createKey);
  const changed = recorderRunIdempotencyKey(scope, { ...intent, browser: 'firefox' }, storage, createKey);
  clearRecorderRunIdempotencyKey(scope, storage);
  const nextRun = recorderRunIdempotencyKey(scope, { ...intent, browser: 'firefox' }, storage, createKey);

  assert.equal(first, 'run-key-1');
  assert.equal(changed, 'run-key-2');
  assert.equal(nextRun, 'run-key-3');
});

test('a temporary storage failure still reuses the pending key within the current page', () => {
  let next = 0;
  const createKey = () => `run-key-${++next}`;
  const unavailableStorage = {
    getItem: () => { throw new Error('storage unavailable'); },
    setItem: () => { throw new Error('storage unavailable'); },
    removeItem: () => { throw new Error('storage unavailable'); },
  };
  const intent = { project_id: 'project-memory-fallback', nodeids: ['tests/test_search.py::test_search'] };

  const first = recorderRunIdempotencyKey('project-memory-fallback:search', intent, unavailableStorage, createKey);
  const retry = recorderRunIdempotencyKey('project-memory-fallback:search', intent, unavailableStorage, createKey);

  assert.equal(first, 'run-key-1');
  assert.equal(retry, first);
});
