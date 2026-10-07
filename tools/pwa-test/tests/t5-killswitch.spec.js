// T5: emergency stop (tools/sw-killswitch.js served as sw.js).
import {
  test, expect, IS_PROD, readRoot, override, clearOverrides,
  expectLots, expectSearch, openControlled, swState,
} from './helpers.js';

test.describe('emergency stop', () => {
  test.skip(IS_PROD, 'needs the local server');
  test.afterEach(async ({ request }) => clearOverrides(request));

  test('G5-1 removes the worker and the caches; G5-2 the map still works', async ({ launch, request }) => {
    const { page } = await openControlled(launch);
    const installed = await swState(page);
    expect(installed.regs).toBe(1);
    expect(installed.caches.length).toBe(1);

    await override(request, 'sw.js', readRoot('tools/sw-killswitch.js'));
    await page.reload();
    const gone = { regs: 0, caches: [] };
    await expect.poll(() => swState(page), { timeout: 30_000 }).toEqual(gone);
    // index.html registers sw.js again on load; the stop version removes
    // itself again, so it stays at zero.
    await page.waitForTimeout(3000);
    await expect.poll(() => swState(page), { timeout: 10_000 }).toEqual(gone);
    expect(await page.evaluate(() => navigator.serviceWorker.controller)).toBeNull();

    // G5-2
    await expectLots(page);
    await expectSearch(page);
  });
});
