import test from 'node:test';
import assert from 'node:assert/strict';

const { buildProjectDisplayNames } = await import('../src/app/projectSelectionModel.ts');

const project = (id, name = 'Reference QA') => ({ id, name });

test('unique project names remain unchanged', () => {
  const projects = [project('proj_abc123456789', 'Storefront'), project('proj_def123456789', 'Payments')];
  const labels = buildProjectDisplayNames(projects);
  assert.equal(labels.get('proj_abc123456789'), 'Storefront');
  assert.equal(labels.get('proj_def123456789'), 'Payments');
});

test('duplicate project names include stable, distinguishable id suffixes', () => {
  const projects = [project('proj_ec58fd0e508e'), project('proj_27b938c621aa')];
  const labels = buildProjectDisplayNames(projects);
  assert.equal(labels.get('proj_ec58fd0e508e'), 'Reference QA · #0e508e');
  assert.equal(labels.get('proj_27b938c621aa'), 'Reference QA · #c621aa');
  assert.equal(new Set(labels.values()).size, 2);
});

test('duplicate short suffixes expand until the projects are distinguishable', () => {
  const projects = [project('proj_ABCDEF123456'), project('proj_XYZDEF123456')];
  const labels = buildProjectDisplayNames(projects);
  assert.equal(labels.get('proj_ABCDEF123456'), 'Reference QA · #CDEF123456');
  assert.equal(labels.get('proj_XYZDEF123456'), 'Reference QA · #ZDEF123456');
});

test('name comparison ignores surrounding whitespace and case', () => {
  const projects = [project('proj_abc123456', ' Reference QA '), project('proj_def456789', 'reference qa')];
  const labels = buildProjectDisplayNames(projects);
  assert.match(labels.get('proj_abc123456'), /#123456$/);
  assert.match(labels.get('proj_def456789'), /#456789$/);
});
