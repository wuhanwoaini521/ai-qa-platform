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
import { createRequire } from 'node:module';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const srcDir = path.join(root, 'src');
const designSystemStyleEntry = createRequire(path.join(root, 'package.json')).resolve('@self/ui-style/react/style.css');
const designSystemPackageRoot = path.resolve(path.dirname(designSystemStyleEntry), '../..');
const designSystemStyleSources = [
  designSystemStyleEntry,
  ...[...readFileSync(designSystemStyleEntry, 'utf8').matchAll(/@import\s+url\(["']?([^"')]+)["']?\)/g)]
    .map(([, source]) => path.resolve(path.dirname(designSystemStyleEntry), source)),
  path.join(designSystemPackageRoot, 'src/tokens/tokens.css'),
  path.join(designSystemPackageRoot, 'src/theme/background.css'),
];

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

test('app semantic aliases map to package tokens', () => {
  const bridge = read(path.join(srcDir, 'design-system.css'));
  const required = [
    '--canvas: var(--c-bg-soft)',
    '--surface-raised: var(--c-bg)',
    '--surface-inset: var(--c-bg-soft)',
    '--line: var(--c-line)',
    '--ink: var(--c-text-strong)',
    '--brand: var(--c-accent)',
    '--accent-green: var(--c-success)',
    '--primary: var(--c-accent)',
    '--r-card: var(--r-xl)',
  ];
  const missing = required.filter((token) => !bridge.includes(token));
  assert.deepEqual(missing, [], `missing package mappings: ${missing.join(', ')}`);
  assert.ok(bridge.includes(":root[data-theme='dark'] .app-design-system.ds-theme"));
  assert.ok(bridge.includes('--bg-dots: radial-gradient'));
  assert.match(read(path.join(srcDir, 'index.css')), /--toolbar-h:/);
});

test('compact shell markers keep layout separate from the shared palette', () => {
  const css = read(path.join(srcDir, 'index.css'));
  const bridge = read(path.join(srcDir, 'design-system.css'));
  assert.ok(!css.includes('.app-frame.is-graphite'));
  assert.ok(css.includes('.app-frame.is-compact-shell'));
  assert.ok(!css.includes('--dashboard-canvas: #'));
  assert.ok(bridge.includes('--graphite-mint: var(--c-accent)'));
  assert.ok(!bridge.includes('var(--graphite-mint)'));
});

test('every referenced CSS custom property is declared', () => {
  const declared = new Set();
  for (const file of [...sources, ...designSystemStyleSources]) {
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

test('quality pilot preserves native library palette, shadows and control styling', () => {
  const css = read(path.join(srcDir, 'pages/QualityPage.css'));
  assert.doesNotMatch(css, /--(?:c-|sh-)[\w-]+\s*:/, 'consumer must not replace library tokens');
  assert.doesNotMatch(css, /#[\da-f]{3,8}\b|\brgba?\(/i, 'use native library tokens instead of a local palette');
  assert.doesNotMatch(css, /(?:^|\n)\.ds-(?:btn|input|select|checkbox|card)[^{]*\{[^}]*(?:background|box-shadow|border-radius)\s*:/s, 'do not fork native control surfaces globally');
});

test('quality filters use raised library shadows and localize requirement statuses', () => {
  const css = read(path.join(srcDir, 'pages/QualityPage.css'));
  assert.match(css, /\.quality-coverage-search \.ds-input,\s*\.quality-coverage-control \.ds-select\s*\{\s*box-shadow:\s*var\(--sh-raised-xs\)/);
  assert.match(css, /\.quality-coverage-search \.ds-input:focus,[\s\S]*?var\(--sh-input-focus\)/);
  assert.doesNotMatch(css, /!important/);
  const page = read(path.join(srcDir, 'pages/QualityPage.tsx'));
  assert.match(page, /getCoverageStatusLabel\(item\.status\)/);
  assert.match(page, /value=\{status\}.*getCoverageStatusLabel\(status\)/);
  const navigation = read(path.join(srcDir, 'components/Navigation.tsx'));
  assert.match(navigation, /<span className="nav-item-mobile-label"/);
  assert.doesNotMatch(navigation, /!designSystem && <span className="nav-item-mobile-label"/);
  const en = JSON.parse(read(path.join(srcDir, 'i18n/locales/en/quality.json')));
  const zh = JSON.parse(read(path.join(srcDir, 'i18n/locales/zh-CN/quality.json')));
  assert.equal(en.coverageStatusReady, 'Ready');
  assert.equal(en.coverageStatusDraft, 'Draft');
  assert.equal(zh.coverageStatusReady, '就绪');
  assert.equal(zh.coverageStatusDraft, '草稿');
});

test('quality uses the pinned official default surface and package stylesheet', () => {
  const pin = '690a35f47e8354707f914687fb748bdf74be410f';
  const manifest = JSON.parse(read(path.join(root, 'package.json')));
  assert.equal(manifest.dependencies['@self/ui-style'], 'github:wuhanwoaini521/self-ui-style#v0.8.1');
  assert.ok(read(path.join(root, '..', '..', 'pnpm-lock.yaml')).includes(pin), 'lockfile must resolve the pinned latest component commit');
  assert.match(read(path.join(srcDir, 'main.tsx')), /@self\/ui-style\/react\/style\.css/);

  const app = read(path.join(srcDir, 'App.tsx'));
  assert.match(app, /<DesignSystemProvider[\s\S]*className="app-design-system"[\s\S]*locale=\{i18n\.resolvedLanguage \?\? i18n\.language\}[\s\S]*dotted/);
  assert.match(app, /const appContent = authenticated \?/);
  const layout = read(path.join(srcDir, 'app/AppLayout.tsx'));
  assert.doesNotMatch(layout, /DesignSystemProvider/);
  assert.match(layout, /designSystem=\{true\}/);
  assert.match(layout, /compactShell=\{compactShellRoute\}/);
  assert.match(layout, /title=\{qualityRoute \? t\('qualityLocation'\) : title\}/);
  const main = read(path.join(srcDir, 'main.tsx'));
  assert.ok(main.indexOf("@self/ui-style/react/style.css") < main.indexOf("'./index.css'"), 'package primitives load before app fallback and semantic rules');
  assert.ok(main.indexOf("'./index.css'") < main.indexOf("'./design-system.css'"), 'semantic adapter loads after package and app CSS');
  const header = read(path.join(srcDir, 'components/Header.tsx'));
  assert.equal((header.match(/container=\{designSystem \? undefined : document\.body\}/g) ?? []).length, 1, 'only the shared language Select needs conditional portal targeting');
  assert.match(header, /<PopoverContent className="ds-system-panel" align="end"/, 'shared system popover must inherit the provider portal');
  const navigation = read(path.join(srcDir, 'components/Navigation.tsx'));
  assert.match(navigation, /className=\{designSystem \? 'sidebar-nav ds-nav' : 'sidebar-nav'\}/, 'package navigation styling follows the global provider mode');
  assert.match(navigation, /className="ds-sidebar-project-select"/);
  assert.match(navigation, /className=\{designSystem \? 'ds-search ds-sidebar-search' : 'sidebar-search'\}/);
  assert.match(navigation, /className=\{designSystem \? 'ds-palette-input' : 'navigation-palette-input'\}/);
  assert.match(navigation, /container=\{designSystem \? undefined : document\.body\}/);
  const qualityCss = read(path.join(srcDir, 'pages/QualityPage.css'));
  assert.doesNotMatch(qualityCss, /data-surface="workbench"/, 'Quality keeps the official default raised component rules');
  assert.doesNotMatch(qualityCss, /quality-(?:project-select|sidebar-collapse|nav-search|palette-input|system-panel)/, 'shared shell styles must not depend on the lazy Quality stylesheet');
  const designSystemCss = read(path.join(srcDir, 'design-system.css'));
  for (const selector of ['.app-design-system .app-sidebar {', '.app-design-system .sidebar-header {', '.app-design-system .sidebar-nav {', '.app-design-system .navigation-palette {']) {
    assert.ok(designSystemCss.includes(selector), `shared shell selector ${selector} must load globally`);
  }
  const page = read(path.join(srcDir, 'pages/QualityPage.tsx'));
  assert.doesNotMatch(page, /container=\{document\.body\}/, 'quality portals must inherit the provider scope');
});

test('quality uses native tabs, search, progress and status components', () => {
  const page = read(path.join(srcDir, 'pages/QualityPage.tsx'));
  for (const component of ['Tabs', 'TabsList', 'TabsTrigger', 'TabsContent', 'SearchInput', 'Progress', 'Badge']) {
    assert.match(page, new RegExp(`<${component}\\b`));
  }
  assert.doesNotMatch(page, /className="quality-(?:posture|coverage)-progress"/);
  assert.doesNotMatch(page, /status-pill|quality-tab-button|handleQualityTabKeyDown/);
  const app = read(path.join(srcDir, 'App.tsx'));
  assert.match(app, /<DesignSystemProvider[^>]*className="app-design-system"/);
  const layout = read(path.join(srcDir, 'app/AppLayout.tsx'));
  assert.doesNotMatch(layout, /return qualityRoute\s*\?\s*<DesignSystemProvider/);
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
