import test from 'node:test';
import assert from 'node:assert/strict';

const {
  emptyFlow,
  emptyNode,
  insertNode,
  updateNode,
  removeNode,
  moveNode,
  countNodes,
  validateFlow,
  flowFromScenario,
  slugTestName,
} = await import('../src/features/flow-canvas/flowDoc.ts');

const base = () => {
  const flow = emptyFlow('checkout', 'http://127.0.0.1:8099/');
  return { flow, navigateId: flow.nodes[0].id };
};

test('a new flow starts with a navigate node and passes validation once filled', () => {
  const { flow, navigateId } = base();
  assert.equal(flow.nodes.length, 1);
  assert.equal(flow.nodes[0].kind, 'navigate');
  assert.deepEqual(validateFlow(flow).errors, []);

  const broken = updateNode(flow, navigateId, { url: '' });
  assert.ok(validateFlow(broken).errors.includes('errorUrlRequired|navigate'));
});

test('insert, update, remove and move operate on nested branches', () => {
  const { flow } = base();
  const condition = emptyNode('condition');
  condition.condition_value = '#offer';
  const withCondition = insertNode(flow, null, 'then', condition);
  const click = emptyNode('click');
  click.locator_value = '#accept';
  const withBranch = insertNode(withCondition, condition.id, 'then', click);
  assert.equal(countNodes(withBranch.nodes), 3);
  assert.equal(withBranch.nodes[1].then.length, 1);

  const renamed = updateNode(withBranch, click.id, { description: 'accept offer' });
  assert.equal(renamed.nodes[1].then[0].description, 'accept offer');

  const moved = moveNode(renamed, null, 'then', 1, 0);
  assert.equal(moved.nodes[0].kind, 'condition');
  assert.equal(moved.nodes[1].kind, 'navigate');

  const removed = removeNode(moved, condition.id);
  assert.equal(countNodes(removed.nodes), 1);
});

test('non-condition nodes cannot carry branches', () => {
  const { flow } = base();
  const click = emptyNode('click');
  click.locator_value = '#a';
  const withBranches = insertNode(flow, null, 'then', { ...click, then: [emptyNode('click')] });
  assert.ok(validateFlow(withBranches).errors.some((code) => code.startsWith('errorBranchesOnlyOnCondition')));
});

test('fill requires a value or an environment variable', () => {
  const { flow } = base();
  const fill = emptyNode('fill');
  fill.locator_value = '#email';
  const incomplete = insertNode(flow, null, 'then', fill);
  assert.ok(validateFlow(incomplete).errors.some((code) => code.startsWith('errorValueRequired')));

  const withValue = updateNode(incomplete, fill.id, { value: 'a@b.c' });
  assert.deepEqual(validateFlow(withValue).errors, []);

  const withBoth = updateNode(withValue, fill.id, { env_var: 'QA_DATA_EMAIL' });
  assert.ok(validateFlow(withBoth).errors.some((code) => code.startsWith('errorValueOrEnv')));
});

test('empty condition branches only warn', () => {
  const { flow } = base();
  const condition = emptyNode('condition');
  condition.condition_value = '#offer';
  const validated = validateFlow(insertNode(flow, null, 'then', condition));
  assert.deepEqual(validated.errors, []);
  assert.ok(validated.warnings.some((code) => code.startsWith('warnEmptyBranches')));
});

test('scenario seeding creates actions then expectation nodes', () => {
  const flow = flowFromScenario(
    { title: 'Apply a valid discount code', actions: ['open checkout', 'enter code'], expected_outcomes: ['total is 90.00'] },
    'http://127.0.0.1:8099/',
  );
  assert.equal(flow.nodes[0].kind, 'navigate');
  assert.deepEqual(flow.nodes.slice(1).map((node) => node.kind), ['click', 'click', 'assert_visible']);
  assert.equal(flow.test_name, 'test_apply_a_valid_discount_code');
  assert.equal(slugTestName('SCN-004'), 'test_scn_004');
  assert.equal(slugTestName('商品搜索 与 购物车'), 'test_flow_canvas_case');
});
