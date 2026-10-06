import test from 'node:test';
import assert from 'node:assert/strict';

const { flowStartUrl, isNavigationFrameFresh, normalizeTrustedDomains } = await import('../src/pages/browserGoalModel.ts');

test('trusted domains normalize URLs and comma-separated hostnames', () => {
  assert.deepEqual(
    normalizeTrustedDomains('https://www.selenium.dev/docs, shop.example.com/path，https://selenium.dev'),
    ['selenium.dev', 'shop.example.com'],
  );
});

test('trusted domains reject unsafe schemes, credentials, and malformed hosts', () => {
  assert.deepEqual(
    normalizeTrustedDomains('javascript:alert(1), https://user:secret@evil.example, not-a-domain'),
    [],
  );
});

test('browser agent waits for a frame newer than the navigation success event', () => {
  assert.equal(isNavigationFrameFresh(8, 9), false);
  assert.equal(isNavigationFrameFresh(9, 9), true);
  assert.equal(isNavigationFrameFresh(2), true);
});

test('natural language start URL preserves explicit IPv4 addresses, ports, and paths', () => {
  assert.equal(
    flowStartUrl('访问 http://127.0.0.1:8765/index.html，点击 WebDriver 文档', 'about:blank'),
    'http://127.0.0.1:8765/index.html',
  );
});

test('natural language start URL supports bare localhost and domains without mistaking an explicit URL path for a host', () => {
  assert.equal(flowStartUrl('打开 localhost:8765/index.html', ''), 'https://localhost:8765/index.html');
  assert.equal(flowStartUrl('访问 uniqlo.com 页面', ''), 'https://uniqlo.com/');
  assert.equal(flowStartUrl('打开 https://user:secret@example.com/index.html', 'https://safe.example/'), 'https://safe.example/');
});
