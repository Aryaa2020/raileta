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
    const context = await browser.newContext({ reducedMotion: 'reduce' });
    for (const path of ['/', '/controller/', '/station/', '/api/v1/health']) {
      assert.equal((await context.request.get(base + path)).status(), 200, 'Public route should load without login');
    }
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
    const status = await health.json();
    assert.equal(status.data_mode, 'corridor_simulation');
    assert.equal(status.model_version, 'mas-sbc-synthetic-v1');
    const corridor = await context.request.get(base + '/api/v1/corridor/MAS-SBC');
    assert.equal(corridor.status(), 200);
    const roster = await corridor.json();
    assert.deepEqual(roster.trains.map(t => String(t.train_number)).sort(), ['12027', '12607', '12639', '12657']);
    const eta = await context.request.get(base + '/api/v1/eta/12027');
    assert.equal(eta.status(), 200);
    const report = await eta.json();
    assert.equal(report.journey.mode, 'simulation');
    assert.deepEqual(report.journey.stops.map(s => s.station_code), ['MAS', 'KPD', 'JTJ', 'BNC', 'SBC']);
    assert.ok(report.journey.stops.every(s => s.platform == null));
    for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      await page.goto(base + '/');
      const operations = page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Operations', exact: true });
      assert.equal(await operations.getAttribute('href'), '/controller/');
      await page.locator('.roster-train').filter({ hasText: '12027' }).click();
      await page.locator('.report-region .jt-detail').waitFor();
      assert.ok((await page.locator('.report-region .jt-detail').innerText()).includes('SIMULATION ONLY'));
      assert.equal(await page.locator('.report-region .jt-detail > .jt-table-scroll tbody tr').count(), 5);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Passenger fits viewport');
      await page.goto(base + '/controller/');
      await page.locator('.overview-train').filter({ hasText: '12027' }).click();
      await page.locator('.ops-detail-column .jt-detail').waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Controller fits viewport');
    }
    assert.deepEqual(errors, [], 'No browser runtime errors');
    console.log('PASS: public HTTPS dashboards/API, simulation model/roster, same-origin navigation and desktop/mobile journey dashboards.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
