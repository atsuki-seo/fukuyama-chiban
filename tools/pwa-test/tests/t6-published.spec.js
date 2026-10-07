// G6-1b: the published site serves the PWA files and nothing from the
// repository-only paths. G6-1 is G1-1 and G1-2 run with BASE_URL
// (npm run test:prod runs every @prod test).
import { test, expect, IS_PROD } from './helpers.js';

test.describe('published files @prod', () => {
  test.skip(!IS_PROD, 'only against the published site (set BASE_URL)');

  test('G6-1b site files are 200, repository-only files are 404', async ({ request }) => {
    const manifest = await request.get('manifest.webmanifest');
    expect(manifest.status()).toBe(200);
    const icons = (await manifest.json()).icons.map(i => i.src);
    for (const file of ['sw.js', 'offline.html', 'icons/apple-touch-icon.png', ...icons]) {
      expect((await request.get(file)).status(), file).toBe(200);
    }
    for (const file of ['plans/pwa.md', 'tools/serve.py']) {
      expect((await request.get(file)).status(), file).toBe(404);
    }
  });
});
