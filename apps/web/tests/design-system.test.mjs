/**
 * Design-system contract tests.
 *
 * These are the invariants a redesign has to keep honest; they catch the kind of drift that makes
 * eleven CSS files and two hundred components slowly disagree with each other:
 *   1. the app must not depend on an external host to render (air-gapped installs, CSP, CI),
 *   2. the core token set must exist,
 *   3. every var(--token) reference must resolve to a declared token (typo/dead-token detection),
 *   4. type must come from the two font tokens, not from ad-hoc font stacks.
 */
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = path.join(root, 'src');

function walk(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

const sources = walk(srcDir).filter((file) => /\.(css|tsx?|mjs)$/.test(file));
const read = (file) => readFileSync(file, 'utf8');
const relative = (file) => path.relative(root, file).split(path.sep).join('/');

test('index.html does not load resources from an external host', () => {
  const html = read(path.join(root, 'index.html'));
  const external = [...html.matchAll(/(?:src|href)\s*=\s*["'](https?:\/\/[^"']+)["']/g)].map((m) => m[1]);
  assert.deepEqual(external, [], `external resources are not allowed (found ${external.join(', ')})`);
});

test('the core design tokens are declared once, in index.css', () => {
  const css = read(path.join(srcDir, 'index.css'));
  const required = [
    '--surface',
    '--surface-raised',
    '--surface-inset',
    '--line',
    '--line-strong',
    '--ink',
    '--ink-soft',
    '--ink-muted',
    '--accent-blue',
    '--accent-green',
    '--accent-amber',
    '--accent-red',
    '--accent-violet',
    '--font-sans',
    '--font-mono',
    '--r-card',
    '--r-lg',
    '--sp-1',
    '--sp-7',
    '--sidebar-w',
    '--toolbar-h',
    '--ease',
    '--dur',
  ];
  const missing = required.filter((token) => !new RegExp(`^\\s*${token}:`, 'm').test(css));
  assert.deepEqual(missing, [], `missing tokens: ${missing.join(', ')}`);
});

test('every referenced CSS custom property is declared', () => {
  const declared = new Set();
  for (const file of sources) {
    const text = read(file);
    for (const match of text.matchAll(/(?:^|[\s;{(])(--[a-z][a-z0-9-]*)\s*:/g)) declared.add(match[1]);
    // Tokens set from JSX (style={{ '--workspace-context-width': ... }}) or via setProperty().
    for (const match of text.matchAll(/['"`](--[a-z][a-z0-9-]*)['"`]/g)) declared.add(match[1]);
  }
  const unknown = new Map();
  for (const file of sources) {
    const text = read(file);
    for (const match of text.matchAll(/var\(\s*(--[a-z][a-z0-9-]*)/g)) {
      const token = match[1];
      if (declared.has(token)) continue;
      if (!unknown.has(token)) unknown.set(token, []);
      unknown.get(token).push(relative(file));
    }
  }
  const report = [...unknown.entries()].map(([token, files]) => `${token} (${[...new Set(files)].join(', ')})`);
  assert.deepEqual(report, [], `undeclared custom properties: ${report.join('; ')}`);
});

test('typography uses the font tokens instead of ad-hoc stacks', () => {
  const offenders = [];
  for (const file of sources) {
    if (file.endsWith(path.join('src', 'index.css'))) continue; // the token block itself
    const text = read(file);
    for (const match of text.matchAll(/font-family\s*:\s*([^;}\n]+)/g)) {
      const value = match[1].trim();
      if (value === 'inherit' || /^var\(--font-(sans|mono)\)$/.test(value)) continue;
      offenders.push(`${relative(file)}: font-family: ${value}`);
    }
    for (const match of text.matchAll(/fontFamily\s*:\s*['"]([^'"]+)['"]/g)) {
      if (/var\(--font-(sans|mono)\)/.test(match[1]) || match[1] === 'inherit') continue;
      offenders.push(`${relative(file)}: fontFamily: ${match[1]}`);
    }
  }
  assert.deepEqual(offenders, [], `use var(--font-sans)/var(--font-mono): ${offenders.join('; ')}`);
});
