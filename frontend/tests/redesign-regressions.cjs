// Local browser verification for the redesign. Requires all three
// Vite apps and the backend. Override RAILETA_PLAYWRIGHT_PATH if needed.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');
const path = require('node:path');

async function assertLayout(page) {
  const result = await page.evaluate(() => ({
    width: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    blurred: [...document.querySelectorAll('*')].filter(el => getComputedStyle(el).backdropFilter !== 'none' && !el.matches('.app-shell .site-nav')).map(el => el.className),
    inert: document.querySelectorAll('[inert]').length,
  }));
  assert.ok(result.scrollWidth <= result.width, `Horizontal overflow: ${JSON.stringify(result)}`);
  assert.deepEqual(result.blurred, [], 'Only the passenger header may use backdrop blur');
  assert.equal(result.inert, 0, 'Content must be available without a scroll-unlock animation');
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const errors = [];
  const checks = [];
  try {
    const context = await browser.newContext({ reducedMotion: 'reduce' });
    await context.route('**/*', route => ['localhost', '127.0.0.1'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const roster = await (await page.request.get('http://127.0.0.1:8000/api/v1/corridor/MAS-SBC')).json();
    assert.ok(roster.trains.length >= 2);
    const [first, second] = roster.trains;
    const profiles = {};
    for (const train of [first, second]) profiles[train.train_number] = await (await page.request.get(`http://127.0.0.1:8000/api/v1/eta/${train.train_number}`)).json();
    await page.route('**/api/v1/corridor/**', route => route.fulfill({ json: roster }));
    await page.route('**/api/v1/eta/**', async route => {
      const number = route.request().url().split('/').at(-1);
      await route.fulfill(profiles[number] ? { json: profiles[number] } : { status: 404, json: { detail: 'Train not found. Check the number and try again.' } });
    });
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 768, height: 1024 }, { width: 390, height: 844 }, { width: 320, height: 568 }, { width: 844, height: 390 }]) {
      await page.setViewportSize(viewport);
      await page.goto('http://127.0.0.1:3000/');
      await page.getByText('Held-out train profiles', { exact: true }).waitFor();
      await assertLayout(page);
      assert.equal(await page.locator('.hero').evaluate(el => getComputedStyle(el).opacity), '1');
      if (viewport.width === 1440 || viewport.width === 390) await page.screenshot({ path: path.resolve(`logs/redesign-passenger-${viewport.width}.png`), fullPage: true });
      if (viewport.width <= 760) {
        await page.getByRole('button', { name: 'Toggle navigation' }).click();
        assert.equal(await page.getByRole('button', { name: 'Toggle navigation' }).getAttribute('aria-expanded'), 'true');
        await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Train explorer' }).click();
        assert.equal(await page.getByRole('button', { name: 'Toggle navigation' }).getAttribute('aria-expanded'), 'false');
      } else await page.locator('.hero-actions').getByRole('link', { name: 'Explore trains' }).click();
      const input = page.getByRole('textbox', { name: 'Train number' });
      await input.fill(first.train_number);
      await input.press('Enter');
      await page.locator('.report-region dt').filter({ hasText: /^Past average delay$/ }).waitFor();
      await assertLayout(page);
      if (viewport.width === 390) {
        await page.locator('.report-region').screenshot({ path: path.resolve('logs/redesign-profile-mobile.png') });
      }
      await page.getByRole('button', { name: 'Back to trains' }).click();
      await page.locator('.roster-train').filter({ hasText: first.train_number }).click();
      await page.locator('.report-region dt').filter({ hasText: /^Past average delay$/ }).waitFor();
      await page.locator('.site-nav .rail-brand').click();
      await page.waitForFunction(() => scrollY === 0);
      assert.equal(await page.locator('.report-region dt').filter({ hasText: /^Past average delay$/ }).count(), 0);
      await input.fill('99999');
      await input.press('Enter');
      await page.getByRole('alert').filter({ hasText: 'Train not found' }).waitFor();
      await page.getByRole('button', { name: 'Back to trains' }).click();
      await page.getByText('Held-out train profiles', { exact: true }).waitFor();
      checks.push(`Passenger ${viewport.width}×${viewport.height}: layout, menu, search, cards, home, and error recovery`);
    }
    // Returning to the list during a slow request must not reopen the old train.
    let release;
    const delayed = new Promise(resolve => { release = resolve; });
    await page.route('**/api/v1/eta/**', async route => { await delayed; await route.fulfill({ json: profiles[first.train_number] }).catch(() => {}); });
    await page.locator('.roster-train').filter({ hasText: first.train_number }).click();
    await page.getByText('Finding the full picture…').waitFor();
    await page.getByRole('button', { name: 'Back to trains' }).click();
    release();
    await page.waitForResponse(response => response.url().includes('/eta/'));
    await page.getByText('Held-out train profiles', { exact: true }).waitFor();
    assert.equal(await page.locator('.report-region dt').filter({ hasText: /^Past average delay$/ }).count(), 0);
    checks.push('Cancelled passenger selection cannot be reopened by a late response');

    for (const [port, name, ready] of [[3002, 'controller', '.overview-train'], [3001, 'station', '.board-source']]) {
      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 });
        await page.goto(`http://127.0.0.1:${port}/`);
        await page.locator(ready).first().waitFor();
        await assertLayout(page);
        if (width !== 320) await page.screenshot({ path: path.resolve(`logs/redesign-${name}-${width}.png`), fullPage: true });
      }
      checks.push(`${name}: desktop and mobile layouts, solid surfaces`);
    }
    // Exercise the event/departure layouts even though the running backend is
    // historical. This fixture is test-only and never enters production data.
    await page.route('**/api/v1/stations/**', route => route.fulfill({ json: { data_mode: 'simulated', departures: [{ train_number: '12007', train_name: 'Test service', destination: 'KSR Bengaluru', scheduled_departure: '14:00', predicted_departure: '14:15', delay_minutes: 15, platform: 2, status: 'scheduled' }] } }));
    await page.reload();
    await page.getByText('LATE 15M', { exact: true }).waitFor();
    await page.getByRole('combobox', { name: 'Station' }).selectOption('KPD');
    await page.getByRole('heading', { name: 'KATPADI JUNCTION', exact: true }).waitFor();
    await page.keyboard.press('3');
    await page.getByRole('heading', { name: 'KSR BENGALURU', exact: true }).waitFor();
    await assertLayout(page);
    checks.push('Station event board: departure rows, station dropdown, keyboard selection');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, checks }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
