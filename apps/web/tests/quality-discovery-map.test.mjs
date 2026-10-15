import test from 'node:test';
import assert from 'node:assert/strict';
import { gapsForCoverageRow, sourceRequirementId } from '../src/features/workspace/qualityDiscoveryMap.ts';

test('discovery navigation resolves feature references to the saved requirement source', () => {
  const requirements = [{ id: 'req-a:REQ-001', source_id: 'req-a' }, { id: 'pasted:REQ-001', source_id: 'PASTED' }];
  assert.equal(sourceRequirementId(['req-a:REQ-001'], requirements), 'req-a');
  assert.equal(sourceRequirementId(['pasted:REQ-001'], requirements), undefined);
  assert.equal(sourceRequirementId(['missing'], requirements, 'draft-a'), 'draft-a');
  assert.equal(sourceRequirementId([], requirements), undefined);
});

test('quality map gaps stay attached to their exact feature or referenced requirement', () => {
  const gaps = [{ item_id: 'feature-a' }, { item_id: 'req-a:REQ-001:AC-001' }, { item_id: 'req-b:REQ-001' }];
  assert.deepEqual(gapsForCoverageRow({ feature_id: 'feature-a' }, gaps, ['req-a:REQ-001']), gaps.slice(0, 2));
});
