import assert from 'node:assert/strict';
import test from 'node:test';
import { defaultWorkspaceTestFile } from '../src/features/automation-studio/defaultWorkspaceTestFile.ts';

test('chooses the first test module deterministically and ignores non-test files', () => {
  assert.equal(
    defaultWorkspaceTestFile(['tests/test_z.py', 'README.md', 'tests/test_a.py']),
    'tests/test_a.py',
  );
  assert.equal(defaultWorkspaceTestFile(['tests\\test_b.py']), 'tests/test_b.py');
  assert.equal(defaultWorkspaceTestFile(['README.md', 'src/module.py']), null);
});
