// Credentials are read locally, never logged or embedded in URLs.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const base = process.env.RAILETA_TEST_URL;
  assert.ok(base?.startsWith('https://'), 'Use the public HTTPS URL');
  const secrets = fs.readFileSync(process.env.RAILETA_ACCESS_FILE, 'utf8');
  const httpCredentials = {
    username: secrets.match(/^Username: (.+)$/m)[1].trim(),
    password: secrets.match(/^Password: (.+)$/m)[1].trim(),
  };
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    const context = await browser.newContext({ httpCredentials });
    const errors = [];
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    for (const path of ['/', '/controller/', '/station/']) {
      const response = await page.goto(base + path);
      assert.equal(response.status(), 200);
      await page.waitForTimeout(1500);
      assert.ok((await page.locator('body').innerText()).length > 100);
      console.log('Dashboard loaded:', path);
    }
    const health = await context.request.get(base + '/api/v1/health');
    assert.equal(health.status(), 200);
    const corridor = await context.request.get(base + '/api/v1/corridor/MAS-SBC');
    assert.equal(corridor.status(), 200);
    const roster = await corridor.json();
    assert.ok(roster.trains.length > 0, 'Replay must populate the roster');
    console.log('Available historical profiles:', roster.trains.length);
    const train = roster.trains[0];
    const eta = await context.request.get(base + '/api/v1/eta/' + train.train_number);
    assert.equal(eta.status(), 200);
    for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      await page.goto(base + '/');
      await page.mouse.wheel(0, 2200);
      await page.waitForFunction(() => document.querySelector('#top').classList.contains('journey-stage-dashboard'));
      const search = await page.locator('.search-panel').boundingBox();
      assert.ok(search.y >= 0 && search.y + search.height < viewport.height, 'Search fits viewport');
      await page.mouse.wheel(0, -3000);
      await page.waitForFunction(() => document.querySelector('#top').classList.contains('journey-stage-cover'));
    }
    assert.deepEqual(errors, [], 'No browser runtime errors');
    console.log('Public HTTPS, authenticated API/model output and desktop/mobile scroll checks passed.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
