const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
      const page = await browser.newPage({ viewport });
      // The cover's animation must not depend on the backend being available.
      await page.route('**/api/v1/corridor/**', route => route.fulfill({
        json: { data_mode: 'historical_replay', trains: [], total_trains: 0 },
      }));
      await page.goto('http://127.0.0.1:4173/');
      const logo = page.locator('.cover-train-mark');
      const initial = await logo.boundingBox();
      const distance = await page.evaluate(() => document.querySelector('.scroll-scene').offsetHeight - document.querySelector('.scene-viewport').clientHeight);
      for (let step = 0; step < 3; step++) {
        await page.mouse.wheel(0, distance / 5);
        await page.waitForTimeout(200);
        const current = await logo.boundingBox();
        assert.ok(Math.abs(current.x - initial.x) < 1, 'Cover train must not slide horizontally');
        assert.equal(await logo.evaluate(element => getComputedStyle(element).transform), 'none', 'Cover train must not rotate or translate independently');
      }
      await page.mouse.wheel(0, 2000);
      await page.waitForFunction(() => document.querySelector('#top').classList.contains('journey-stage-dashboard'));
      const search = await page.locator('.search-panel').boundingBox();
      assert.ok(search.y >= 16 && search.y + search.height < viewport.height, 'Search must remain fully on-screen');
      await page.waitForTimeout(200);
      await page.mouse.wheel(0, -3000);
      await page.waitForFunction(() => document.querySelector('#top').classList.contains('journey-stage-cover'));
      assert.ok(Math.abs((await logo.boundingBox()).x - initial.x) < 1, 'Reverse transition must keep the logo centered');
      await page.close();
    }
    console.log('Cover logo checks passed: no sideways movement or rotation, dashboard reachable, reverse preserved (desktop/mobile).');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
