// T4: install button and iOS steps.
import { devices } from '@playwright/test';
import { test, expect, IS_PROD, openMap, fakeInstallPrompt, blockRealInstallPrompt } from './helpers.js';

// iPhone UA and screen in Chromium.
const { defaultBrowserType, ...IPHONE } = devices['iPhone 15'];

// A profile where only fake beforeinstallprompt events reach the page:
// Chromium fires a real one even without the engagement bypass flag and with
// an iPhone UA, which a real iPhone never does.
async function launchFakeOnly(launch, options) {
  const r = await launch(options);
  await blockRealInstallPrompt(r.context);
  return r;
}

test.describe('install', () => {
  test.skip(IS_PROD, 'needs the local server');

  // Chromium 153 (Chrome for Testing, headless) fires the event with or
  // without --bypass-app-banner-engagement-checks.
  test('G4-1 a real beforeinstallprompt fires and shows the button', async ({ launch }) => {
    const { page } = await launch();
    await openMap(page);
    await expect(page.locator('#install-btn')).toBeVisible({ timeout: 30_000 });
  });

  test('G4-1b (fake event) the button calls prompt()', async ({ launch }) => {
    const { page } = await launchFakeOnly(launch);
    await openMap(page);
    await expect(page.locator('#install-btn')).toBeHidden();
    await fakeInstallPrompt(page);
    await expect(page.locator('#install-btn')).toBeVisible();
    await page.click('#install-btn');
    expect(await page.evaluate(() => window.__prompted)).toBe(true);
    // A prompt event is used once.
    await expect(page.locator('#install-btn')).toBeHidden();
  });

  test('G4-2 appinstalled hides the button', async ({ launch }) => {
    const { page } = await launchFakeOnly(launch);
    await openMap(page);
    await fakeInstallPrompt(page);
    await expect(page.locator('#install-btn')).toBeVisible();
    await page.evaluate(() => window.dispatchEvent(new Event('appinstalled')));
    await expect(page.locator('#install-btn')).toBeHidden();
  });

  test('G4-3 on iPhone the steps show instead of the button', async ({ launch }) => {
    const { page } = await launchFakeOnly(launch, IPHONE);
    await openMap(page);
    await page.click('#panel-open');
    await expect(page.locator('#install-ios')).toBeVisible();
    await expect(page.locator('#install-btn')).toBeHidden();
  });

  test('G4-4a standalone on iPhone (navigator.standalone) shows neither', async ({ launch }) => {
    const { context, page } = await launchFakeOnly(launch, IPHONE);
    await context.addInitScript(() => {
      Object.defineProperty(Navigator.prototype, 'standalone', { get: () => true, configurable: true });
    });
    await openMap(page);
    await page.click('#panel-open');
    await fakeInstallPrompt(page);
    await expect(page.locator('#install-ios')).toBeHidden();
    await expect(page.locator('#install-btn')).toBeHidden();
  });

  test('G4-4b display-mode: standalone shows neither', async ({ launch }) => {
    const { page } = await launchFakeOnly(launch);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'display-mode', value: 'standalone' }] }).catch(() => {});
    await openMap(page);
    const emulated = await page.evaluate(() => matchMedia('(display-mode: standalone)').matches);
    test.skip(!emulated, 'This Chromium cannot emulate display-mode; G4-4c covers the decision');
    await fakeInstallPrompt(page);
    await expect(page.locator('#install-btn')).toBeHidden();
    await expect(page.locator('#install-ios')).toBeHidden();
  });

  test('G4-4c installMode() decision table', async ({ launch }) => {
    const { page } = await launchFakeOnly(launch);
    await openMap(page);
    const got = await page.evaluate(() => [
      [true, true, true], [true, false, true], [true, true, false], [true, false, false],
      [false, false, true], [false, true, true], [false, true, false], [false, false, false],
    ].map(([standalone, ios, canPrompt]) => installMode({ standalone, ios, canPrompt })));
    expect(got).toEqual(['none', 'none', 'none', 'none', 'button', 'button', 'ios', 'none']);
  });
});
