// T0: regression baseline. These also stand for G2-2 (after the share
// button) and G5-2 runs them again after the emergency stop.
import { test, expect, IS_PROD, openMap, expectSearch } from './helpers.js';

test('G0-1 lot features load at the spot', async ({ launch }) => {
  const { page } = await launch();
  await openMap(page);
});

test('G0-2 search finds 青葉台一丁目 4-1', async ({ launch }) => {
  const { page } = await launch();
  await openMap(page);
  await expectSearch(page);
});

test('G0-3 tools/serve.py answers Range with 206', async ({ request }) => {
  test.skip(IS_PROD, 'checks the local server');
  const r = await request.get('chiban_fukuyama_2026_0.pmtiles', { headers: { Range: 'bytes=0-15' } });
  expect(r.status()).toBe(206);
  expect((await r.body()).length).toBe(16);
  expect(r.headers()['content-range']).toMatch(/^bytes 0-15\/\d+$/);
});
