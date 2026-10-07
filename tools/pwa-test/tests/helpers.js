import { test as base, expect, chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { ROOT } from '../check-version.mjs';

export { expect, ROOT };

export const IS_PROD = !!process.env.BASE_URL;

// A spot near Fukuyama Station. 34.490 N lies in the middle latitude band of
// the city lot tiles (chiban_fukuyama_2026_1.pmtiles, 34.456-34.538 N), so
// its source is city-1; city-0 starts at 34.525 N.
export const SPOT = '#map=17/34.490/133.362';
export const SPOT_SOURCE = 'city-1';

export const readRoot = file => fs.readFileSync(path.join(ROOT, file), 'utf8');

export const test = base.extend({
  // Opens a fresh persistent (non-incognito) profile: Chrome reports
  // incognito windows as not installable and never fires
  // beforeinstallprompt there. Every profile is closed after the test.
  launch: async ({ baseURL }, use, testInfo) => {
    const contexts = [];
    await use(async (options = {}) => {
      const dir = testInfo.outputPath(`profile-${contexts.length}`);
      const context = await chromium.launchPersistentContext(dir, {
        // Full Chromium in new headless mode; the headless shell lacks the
        // web app (install) features.
        channel: 'chromium',
        args: ['--bypass-app-banner-engagement-checks'],
        baseURL,
        serviceWorkers: 'allow',
        viewport: { width: 1280, height: 800 },
        ...options,
      });
      contexts.push(context);
      const page = context.pages()[0] || await context.newPage();
      return { context, page };
    });
    for (const c of contexts) await c.close();
  },
});

// ------------------------------------------------------------ tools/serve.py

export async function override(request, file, body) {
  const r = await request.put(`__override__/${file}`, { data: body });
  expect(r.status(), `override ${file}`).toBe(204);
}

export async function clearOverrides(request) {
  if (IS_PROD) return;
  const r = await request.delete('__override__');
  expect(r.status()).toBe(204);
}

// ------------------------------------------------------------ the map page

// G0-1: lot features of the spot are loaded.
export async function expectLots(page) {
  await page.waitForFunction(
    src => typeof map !== 'undefined' && map.isStyleLoaded() &&
      map.querySourceFeatures(src, { sourceLayer: 'chiban' }).length > 0,
    SPOT_SOURCE,
    { timeout: 60_000 },
  );
}

export async function openMap(page, file = '') {
  await page.goto(file + SPOT);
  await expectLots(page);
}

// G0-2: the search finds 青葉台一丁目 4-1. An exact hit is a single result: the
// page says it moves there and puts a marker on it.
export async function expectSearch(page) {
  await page.fill('#q', '青葉台一丁目 4-1');
  await page.click('#search-form button[type=submit]');
  await expect(page.locator('#search-status')).toContainText('青葉台一丁目 4-1 に移動します');
  await expect(page.locator('.maplibregl-marker')).toHaveCount(1);
}

// Loads the map, waits for the service worker, then reloads so that the page
// is controlled by it.
export async function openControlled(launch, options) {
  const r = await launch(options);
  await openMap(r.page);
  await r.page.evaluate(() => navigator.serviceWorker.ready.then(() => {}));
  await r.page.reload();
  await expectLots(r.page);
  return r;
}

// Every service worker registration and cache, read in the page. Returns null
// while the page is navigating.
export async function swState(page) {
  try {
    return await page.evaluate(async () => {
      if (document.readyState !== 'complete') return null;
      const regs = await navigator.serviceWorker.getRegistrations();
      const keys = await caches.keys();
      return { regs: regs.length, caches: keys };
    });
  } catch {
    return null;
  }
}

// Chromium fires a real beforeinstallprompt here even without the engagement
// bypass flag (and with an iPhone UA, which a real iPhone never does). This
// stops the trusted event before the page sees it, so only fake ones count.
export async function blockRealInstallPrompt(context) {
  await context.addInitScript(() => {
    window.addEventListener('beforeinstallprompt', e => {
      if (e.isTrusted) e.stopImmediatePropagation();
    }, true);
  });
}

export async function fakeInstallPrompt(page) {
  await page.evaluate(() => {
    const e = new Event('beforeinstallprompt');
    e.prompt = () => { window.__prompted = true; return Promise.resolve({ outcome: 'accepted' }); };
    window.dispatchEvent(e);
  });
}

// PNG width and height from the IHDR chunk, or null if not a PNG.
export function pngSize(buf) {
  if (buf.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') return null;
  if (buf.subarray(12, 16).toString('latin1') !== 'IHDR') return null;
  return [buf.readUInt32BE(16), buf.readUInt32BE(20)];
}
