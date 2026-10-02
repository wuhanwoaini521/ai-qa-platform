import test from 'node:test';
import assert from 'node:assert/strict';
import { toEditorRange, workspaceSourcePath } from '../src/features/automation-studio/languageProtocol.ts';

test('LSP zero-based ranges preserve multi-line selections in Monaco', () => {
  assert.deepEqual(toEditorRange({start: {line: 0, character: 0}, end: {line: 3, character: 12}}), {startLineNumber: 1, startColumn: 1, endLineNumber: 4, endColumn: 13});
});
test('definition navigation accepts workspace Python paths including Unicode', () => {
  assert.equal(workspaceSourcePath('qa-workspace://proj/tests/test_login.py', 'proj'), 'tests/test_login.py');
  assert.equal(workspaceSourcePath('qa-workspace://proj/tests/%E7%94%A8%E4%BE%8B.py', 'proj'), 'tests/用例.py');
});
test('definition navigation rejects cross-project and host filesystem locations', () => {
  for (const uri of ['file:///C:/secrets.py', 'qa-workspace://other/tests/test.py', 'qa-workspace://project/tests/test.py', 'https://example.com/test.py']) assert.equal(workspaceSourcePath(uri, 'proj'), null);
});
test('definition navigation rejects encoded traversal, malformed escaping and non-source targets', () => {
  for (const path of ['%2E%2E/secrets.py', 'tests/%2e%2e/secrets.py', 'tests%5Ctest.py', 'tests/test.py?secret=1', '%ZZ.py', 'tests/data.json', 'tests//test.py']) assert.equal(workspaceSourcePath(`qa-workspace://proj/${path}`, 'proj'), null);
});
