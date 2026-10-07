// T3: the navigation-only service worker.
import { execFileSync } from 'node:child_process';
import {
  test, expect, IS_PROD, ROOT, SPOT, readRoot, override, clearOverrides,
  openMap, expectLots, expectSearch, openControlled, swState,
} from './helpers.js';
import { versions } from '../check-version.mjs';

const VERSION = versions().sw;
const CACHE = `fukuyama-chiban-${VERSION}`;

test.describe('service worker', () => {
  test.skip(IS_PROD, 'needs the local server');
  test.afterEach(async ({ request }) => clearOverrides(request));

  test('G3-1 the page is controlled, scope is BASE', async ({ launch }) => {
    const { page } = await openControlled(launch);
    const r = await page.evaluate(async () => ({
      controlled: navigator.serviceWorker.controller !== null,
      scope: (await navigator.serviceWorker.getRegistration()).scope,
      base: BASE,
    }));
    expect(r.controlled).toBe(true);
    expect(r.scope).toBe(r.base);
  });

  test('G3-2 the page itself goes through the worker', async ({ launch }) => {
    const { page } = await openControlled(launch);
    const workerStart = await page.evaluate(() => performance.getEntriesByType('navigation')[0].workerStart);
    expect(workerStart).toBeGreaterThan(0);
  });

  test('G3-3 tiles, scripts and search data bypass the worker', async ({ launch }) => {
    const { page } = await launch();
    await openMap(page);
    await page.evaluate(() => navigator.serviceWorker.ready.then(() => {}));
    const seen = [];
    page.on('response', r => seen.push(r));
    await page.reload();
    await expectLots(page);
    expect(await page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
    // The road layer reads GSI's PMTiles; the search reads search*.json.
    await page.check('#lyr-road');
    await page.waitForFunction(() => map.querySourceFeatures('road', { sourceLayer: 'RdCL' }).length > 0, null, { timeout: 60_000 });
    await expectSearch(page);
    await page.waitForFunction(() => map.areTilesLoaded(), null, { timeout: 60_000 });

    const groups = {
      'local PMTiles': r => new URL(r.url()).origin === new URL(page.url()).origin && /\.pmtiles$/.test(new URL(r.url()).pathname),
      'cyberjapandata.gsi.go.jp': r => new URL(r.url()).hostname === 'cyberjapandata.gsi.go.jp',
      'unpkg.com': r => new URL(r.url()).hostname === 'unpkg.com',
      'search*.json': r => /\/search(\/\d+)?\.json$/.test(new URL(r.url()).pathname),
    };
    for (const [name, match] of Object.entries(groups)) {
      const hits = seen.filter(match);
      expect(hits.length, `${name} requests`).toBeGreaterThan(0);
      expect(hits.filter(r => r.fromServiceWorker()).map(r => r.url()), `${name} via the worker`).toEqual([]);
    }
    const pm = seen.filter(groups['local PMTiles']);
    expect(pm.filter(r => r.status() !== 206).map(r => `${r.status()} ${r.url()}`), 'PMTiles not 206').toEqual([]);
  });

  test('G3-4 offline reload shows offline.html', async ({ launch }) => {
    const { context, page } = await openControlled(launch);
    await context.setOffline(true);
    await page.reload();
    await expect(page.locator('[data-offline-page]')).toBeVisible();
    await context.setOffline(false);
  });

  test('G3-5 the only cache holds only offline.html', async ({ launch }) => {
    const { page } = await openControlled(launch);
    const r = await page.evaluate(async () => {
      const out = {};
      for (const k of await caches.keys()) out[k] = (await (await caches.open(k)).keys()).map(q => q.url);
      return { out, offline: new URL('offline.html', BASE).href };
    });
    expect(r.out).toEqual({ [CACHE]: [r.offline] });
  });

  test('G3-6 sw.js VERSION equals APP.version', () => {
    const v = versions();
    expect(v.app).toBeTruthy();
    expect(v.sw).toBe(v.app);
  });

  test('G3-7 a new sw.js takes over and drops the old cache', async ({ launch, request }) => {
    const { page } = await openControlled(launch);
    expect((await swState(page)).caches).toEqual([CACHE]);
    const v2 = `${VERSION}-test2`;
    const src = readRoot('sw.js').replace(`const VERSION = '${VERSION}';`, `const VERSION = '${v2}';`);
    expect(src).toContain(v2);
    await override(request, 'sw.js', src);
    await page.reload();
    await expect.poll(async () => (await swState(page))?.caches, { timeout: 30_000 }).toEqual([`fukuyama-chiban-${v2}`]);
    expect(await page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
  });

  test('G3-8 no more console errors than the main branch', async ({ launch, request }) => {
    const ref = process.env.BASELINE_REF || 'origin/main';
    const before = execFileSync('git', ['show', `${ref}:index.html`], { cwd: ROOT });

    async function errorsOf() {
      const { page } = await launch();
      const errors = [];
      page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('pageerror', e => errors.push(String(e)));
      // index.html by name, so that the override below applies.
      await page.goto(`index.html${SPOT}`);
      await expectLots(page);
      await page.waitForTimeout(2000);
      await page.reload();
      await expectLots(page);
      await page.waitForTimeout(2000);
      return errors;
    }

    await override(request, 'index.html', before);
    const baseline = await errorsOf();
    await clearOverrides(request);
    const now = await errorsOf();
    expect(now.length, `now: ${JSON.stringify(now)}\n${ref}: ${JSON.stringify(baseline)}`).toBeLessThanOrEqual(baseline.length);
  });
});
