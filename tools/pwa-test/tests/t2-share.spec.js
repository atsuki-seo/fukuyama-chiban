// T2: share button. G2-2 is t0-base.spec.js running against this page.
import { test, expect, openMap } from './helpers.js';

test('G2-1 without navigator.share the URL goes to the clipboard', async ({ launch }) => {
  const { context, page } = await launch({ permissions: ['clipboard-read', 'clipboard-write'] });
  await context.addInitScript(() => { delete Navigator.prototype.share; });
  await openMap(page);
  expect(await page.evaluate(() => typeof navigator.share)).toBe('undefined');
  await page.click('#share-btn');
  await expect(page.locator('#toast')).toContainText('コピーしました');
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain('#map=');
  expect(copied).toBe(await page.evaluate(() => location.href));
});
