// T1: manifest, icons and meta tags.
import { test, expect, pngSize } from './helpers.js';

async function getText(request, file) {
  const r = await request.get(file);
  expect(r.status(), file).toBe(200);
  return r.text();
}

test('G1-1 no installability errors @prod', async ({ launch }) => {
  const { page } = await launch();
  await page.goto('');
  const cdp = await page.context().newCDPSession(page);
  await expect.poll(
    async () => (await cdp.send('Page.getInstallabilityErrors')).installabilityErrors,
    { timeout: 30_000 },
  ).toEqual([]);
});

test('G1-2 manifest parses and matches BASE @prod', async ({ launch }) => {
  const { page } = await launch();
  await page.goto('');
  const cdp = await page.context().newCDPSession(page);
  const res = await cdp.send('Page.getAppManifest');
  expect(res.errors).toEqual([]);
  const base = await page.evaluate(() => BASE);
  const m = JSON.parse(res.data);
  // Resolved as the manifest spec does: start_url and scope against the
  // manifest URL; id against start_url's *origin*, and start_url when absent.
  // A relative id such as "./" would become the origin root, which every
  // <user>.github.io site shares, so the manifest leaves id out.
  const startUrl = new URL(m.start_url, res.url).href;
  expect(startUrl).toBe(base);
  expect(new URL(m.scope, res.url).href).toBe(base);
  const id = typeof m.id === 'string' && m.id !== '' ? new URL(m.id, new URL(startUrl).origin).href : startUrl;
  expect(id).toBe(base);
  expect(m.display).toBe('standalone');
  expect(m.lang).toBe('ja');
  // Chrome's own parse, where this Chrome version reports it.
  if (res.manifest) {
    for (const key of ['startUrl', 'scope', 'id']) {
      if (typeof res.manifest[key] === 'string') expect(res.manifest[key], key).toBe(base);
    }
  }
});

test('G1-3 theme_color equals <meta name="theme-color"> @prod', async ({ request }) => {
  const manifest = JSON.parse(await getText(request, 'manifest.webmanifest'));
  const html = await getText(request, '');
  const meta = html.match(/<meta name="theme-color" content="([^"]+)">/);
  expect(meta).not.toBeNull();
  expect(manifest.theme_color.toLowerCase()).toBe(meta[1].toLowerCase());
});

test('G1-4 manifest icons exist with the declared sizes @prod', async ({ request }) => {
  const manifest = JSON.parse(await getText(request, 'manifest.webmanifest'));
  const sizes = [];
  for (const icon of manifest.icons) {
    const r = await request.get(icon.src);
    expect(r.status(), icon.src).toBe(200);
    const size = pngSize(await r.body());
    expect(size, `${icon.src} is a PNG`).not.toBeNull();
    expect(`${size[0]}x${size[1]}`, icon.src).toBe(icon.sizes);
    sizes.push(icon.sizes);
  }
  expect(sizes).toContain('192x192');
  expect(sizes).toContain('512x512');
  expect(manifest.icons.some(i => (i.purpose || '').split(/\s+/).includes('maskable'))).toBe(true);
});

test('G1-5 apple-touch-icon is a 180x180 PNG @prod', async ({ request }) => {
  const html = await getText(request, '');
  const link = html.match(/<link rel="apple-touch-icon" href="([^"]+)">/);
  expect(link).not.toBeNull();
  const r = await request.get(link[1]);
  expect(r.status()).toBe(200);
  expect(pngSize(await r.body())).toEqual([180, 180]);
});
