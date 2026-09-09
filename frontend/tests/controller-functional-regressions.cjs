// Local-only UI checks. Requires controller :3002 and backend :8000.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const checks = [];
  const errors = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
    await context.route('**/*', route => ['localhost', '127.0.0.1'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const realRoster = await (await page.request.get('http://127.0.0.1:8000/api/v1/corridor/MAS-SBC')).json();
    const realProfile = await (await page.request.get(`http://127.0.0.1:8000/api/v1/eta/${realRoster.trains[0].train_number}`)).json();
    let roster = realRoster;
    let profile = realProfile;
    await page.route('**/api/v1/corridor/**', route => route.fulfill({ json: roster }));
    await page.route('**/api/v1/eta/**', route => route.fulfill({ json: profile }));
    const layout = async () => {
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal page overflow');
      const animated = await page.locator('.ops-app').evaluate(root => [...root.querySelectorAll('*')].filter(el => {
        const style = getComputedStyle(el);
        return style.animationName !== 'none' || style.transitionDuration.split(',').some(value => parseFloat(value) > 0) || style.backdropFilter !== 'none';
      }).map(el => el.className));
      assert.deepEqual(animated, [], 'No animation, transitions, or glass surfaces');
    };
    for (const width of [1440, 1100, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto('http://127.0.0.1:3002/');
      await page.locator('.overview-train').first().waitFor();
      await page.getByRole('heading', { name: 'Train overview', exact: true }).waitFor();
      assert.equal(await page.locator('.reveal-char').count(), 0);
      await layout();
      if (width === 1440) await page.screenshot({ path: path.resolve('logs/controller-functional-overview.png'), fullPage: true });
      await page.locator('.overview-train').filter({ hasText: realProfile.train_number }).click();
      await page.getByRole('heading', { name: realProfile.train_name, exact: true }).waitFor();
      assert.deepEqual(await page.locator('.ops-report-metrics dt').allTextContents(), ['Past average delay', 'RailETA estimate', 'Difference']);
      assert.equal(await page.locator('.train-focus-panel details').getAttribute('open'), null);
      const round = value => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(value) + ' min';
      assert.deepEqual(await page.locator('.ops-report-metrics dd').allTextContents(), [realProfile.historical_replay.recorded_average_delay_minutes, realProfile.historical_replay.predicted_average_delay_minutes, realProfile.historical_replay.absolute_error_minutes].map(round));
      if (width >= 1100) assert.ok(await page.evaluate(() => Math.abs(document.querySelector('.corridor-panel').getBoundingClientRect().top - document.querySelector('.train-focus-panel').getBoundingClientRect().top) < 5), 'List and detail sit side by side');
      await layout();
      if ([1440, 390].includes(width)) {
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
        await page.waitForFunction(() => window.scrollY === 0);
        await page.screenshot({ path: path.resolve(`logs/controller-functional-selected-${width}.png`), fullPage: true });
      }
      await page.locator('.train-focus-panel summary').focus();
      await page.keyboard.press('Enter');
      await page.getByRole('heading', { name: 'Test results', exact: true }).waitFor();
      await layout();
      await page.getByRole('button', { name: 'Close train view' }).click();
      assert.equal(await page.locator('.overview-train.is-selected').count(), 0);
      checks.push(`${width}px: readable layout, selected report, accurate metrics, keyboard disclosure, close, no motion`);
    }
    // Deterministic test-only data covers every delay band and missing values.
    roster = { ...realRoster, trains: [
      { train_number: '10001', train_name: 'Alpha', current_station: 'MAS', delay_minutes: 0 },
      { train_number: '10002', train_name: 'Beta', current_station: 'KPD', delay_minutes: 10 },
      { train_number: '10003', train_name: 'Gamma', current_station: 'SBC', delay_minutes: 30 },
      { train_number: '10004', train_name: 'Delta', current_station: null, delay_minutes: null },
    ] };
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.reload();
    await page.locator('.overview-train').filter({ hasText: 'Alpha' }).waitFor();
    assert.deepEqual(await page.locator('.ops-stat strong').allTextContents(), ['4', '1', '1', '1']);
    for (const [filter, name] of [['low', 'Alpha'], ['medium', 'Beta'], ['high', 'Gamma'], ['unknown', 'Delta']]) {
      await page.getByRole('combobox', { name: 'Filter by delay' }).selectOption(filter);
      assert.equal(await page.locator('.overview-train').count(), 1);
      assert.equal(await page.locator('.overview-train strong').innerText(), name);
    }
    await page.getByRole('combobox', { name: 'Filter by delay' }).selectOption('all');
    await page.getByRole('combobox', { name: 'Sort trains' }).selectOption('delay');
    assert.deepEqual(await page.locator('.overview-train strong').allTextContents(), ['Gamma', 'Beta', 'Alpha', 'Delta']);
    for (const query of ['bEtA', '10002', 'kpd']) {
      await page.getByRole('searchbox', { name: 'Search trains' }).fill(query);
      assert.equal(await page.locator('.overview-train strong').innerText(), 'Beta');
    }
    await page.getByRole('searchbox', { name: 'Search trains' }).fill('no match');
    await page.getByRole('button', { name: 'Clear filters' }).click();
    assert.equal(await page.locator('.overview-train').count(), 4);
    const refresh = page.getByRole('button', { name: 'Refresh corridor and selected train' });
    await refresh.hover();
    assert.equal(await page.locator('.kiro-button-fill').evaluate(el => getComputedStyle(el).display), 'none');
    await layout();
    checks.push('Search by name/number/station, all delay bands, missing values, sorting, reset, static hover');
    // Existing station-event workflows remain available with explicit prototype labels.
    roster = { ...roster, data_mode: 'simulated' };
    profile = { train_number: '10001', train_name: 'Alpha', data_mode: 'simulated', current_status: {}, route_stops: [], upcoming_stations: [] };
    await page.reload();
    await page.locator('.overview-train').filter({ hasText: 'Alpha' }).click();
    await page.getByRole('heading', { name: 'Alpha', exact: true }).waitFor();
    assert.equal(await page.locator('.progress-ring').innerText(), '—');
    assert.equal(await page.locator('.ops-map-disclosure').getAttribute('open'), null);
    await page.locator('.ops-map-disclosure summary').click();
    await page.getByText('Station-coordinate schematic is unavailable from the latest source snapshot.').waitFor();
    await layout();
    checks.push('Event mode: missing status handled, no fabricated progress, optional map');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, checks }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
