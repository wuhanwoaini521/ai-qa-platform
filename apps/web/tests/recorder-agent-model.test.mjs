import test from 'node:test';
import assert from 'node:assert/strict';

const { recorderStepsFromAgent } = await import('../src/pages/recorderAgentModel.ts');

const locator = { kind: 'role', value: 'textbox', name: 'Search', exact: true };

test('converts verified Browser Agent actions, including Enter, into executable recorder steps', () => {
  const generated = recorderStepsFromAgent({
    kind: 'ai_jev_browser_agent',
    verified: true,
    final_title: 'Selenium Documentation',
    actions: [
      { action: 'fill', status: 'success', target: 'Search', locator, locator_verified: true, value: 'Selenium', decision_provider: 'single-candidate' },
      { action: 'press_key', status: 'partial', target: 'Search', locator, locator_verified: true, value: 'Enter', decision_provider: 'jev', decision_confidence: 0.94 },
      { action: 'click', status: 'success', target: 'WebDriver docs', locator: { kind: 'role', value: 'link', name: 'WebDriver' }, locator_verified: true },
    ],
    goal_evidence: { visible_text_criteria: ['Selenium'], completion_evidence: ['WebDriver', 'Selenium'] },
  }, 'https://www.baidu.com');

  assert.ok(generated);
  assert.deepEqual(generated.steps.map(({ action }) => action), ['navigate', 'fill', 'press', 'click', 'assert_text', 'assert_text']);
  assert.equal(generated.steps[0].url, 'https://www.baidu.com/');
  assert.equal(generated.steps[2].key, 'Enter');
  assert.equal(generated.steps[2].locator_decision.provider, 'Jev');
  assert.equal(generated.steps[2].locator_decision.confidence, 0.94);
  assert.equal(generated.actionCount, 3);
  assert.equal(generated.jevCount, 1);
  assert.equal(generated.assertionCount, 2);
});

test('excludes failed, unexpected, inspect, and unverified element actions', () => {
  const generated = recorderStepsFromAgent({
    kind: 'ai_jev_browser_agent',
    verified: true,
    actions: [
      { action: 'click', status: 'success', target: 'unsafe', locator, locator_verified: false },
      { action: 'click', status: 'unexpected', target: 'unexpected', locator, locator_verified: true },
      { action: 'click', status: 'failed', target: 'failed', locator, locator_verified: true },
      { action: 'inspect', status: 'partial' },
      { action: 'wait', status: 'partial', value: '25' },
    ],
  }, 'example.com');

  assert.ok(generated);
  assert.deepEqual(generated.steps.map(({ action }) => action), ['navigate', 'wait']);
  assert.equal(generated.steps[1].value, '100');
  assert.equal(generated.actionCount, 1);
});

test('does not generate a script from unverified task output or an unsafe start URL', () => {
  const output = { kind: 'ai_jev_browser_agent', verified: true, actions: [] };
  assert.equal(recorderStepsFromAgent({ ...output, verified: false }, 'https://example.com'), null);
  assert.equal(recorderStepsFromAgent(output, 'javascript:alert(1)'), null);
  assert.equal(recorderStepsFromAgent({ ...output, kind: 'local_strategy' }, 'https://example.com'), null);
});
