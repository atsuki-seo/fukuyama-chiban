import { defineConfig } from '@playwright/test';

const PORT = Number(process.env.PWA_TEST_PORT || 8766);
// Set BASE_URL (with a trailing slash) to test a published site; only the
// tests tagged @prod make sense there (npm run test:prod).
const PROD = process.env.BASE_URL;

export default defineConfig({
  testDir: './tests',
  // tools/serve.py overrides are shared state, so tests run one at a time.
  workers: 1,
  fullyParallel: false,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: [['list']],
  use: { baseURL: PROD || `http://localhost:${PORT}/` },
  webServer: PROD ? undefined : {
    command: `python3 ../serve.py --port ${PORT} --allow-override`,
    url: `http://localhost:${PORT}/index.html`,
    reuseExistingServer: false,
    env: { SERVE_QUIET: '1' },
  },
});
