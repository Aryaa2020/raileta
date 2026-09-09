// Run against the locally built controller/station apps; external requests are blocked.
// API fixtures start from the running local backend and are varied only to test UI failures.
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const checks = [];
  try {
    const roster = await (await page.request.get('http://127.0.0.1:8000/api/v1/corridor/MAS-SBC')).json();
    assert.ok(roster.trains.length >= 2, 'Need two locally replayed profiles for UI testing');
    const [first, second] = roster.trains;
    const profiles = {};
    for (const train of [first, second]) profiles[train.train_number] = await (await page.request.get(`http://127.0.0.1:8000/api/v1/eta/${train.train_number}`)).json();
    let empty = false;
    let failDetail = true;
    let detailCalls = 0;
    let slowFirst = false;
    let refreshed = false;
    await page.route('**/api/v1/corridor/**', async route => {
      await wait(100);
      await route.fulfill({ json: empty ? { ...roster, trains: [], total_trains: 0 } : roster });
    });
    await page.route('**/api/v1/eta/**', async route => {
      ++detailCalls;
      const number = route.request().url().split('/').at(-1);
      await wait(slowFirst && number === first.train_number ? 500 : 200);
      await route.fulfill(failDetail ? { status: 503, json: { detail: 'Test-only unavailable response' } } : {
        json: { ...profiles[number], train_name: profiles[number].train_name + (refreshed ? ' refreshed' : '') },
      }).catch(() => {}); // Selection changes deliberately cancel the old request.
    });
    await page.goto('http://127.0.0.1:3002/');
    await page.locator('.overview-train').filter({ hasText: first.train_number }).click();
    await page.getByRole('heading', { name: `Loading train ${first.train_number}` }).waitFor();
    await page.getByText('Selected train refresh failed. Its last report may be stale.', { exact: true }).waitFor();
    assert.equal(await page.locator('.overview-train.is-selected').getAttribute('aria-pressed'), 'true');
    checks.push('selection is highlighted during loading and failure');

    const refresh = page.getByRole('button', { name: 'Refresh corridor and selected train', exact: true });
    const before = detailCalls;
    await refresh.click();
    assert.equal(await refresh.isDisabled(), true);
    await page.waitForFunction(() => !document.querySelector('[title="Refresh corridor and selected train"]').disabled);
    assert.ok(detailCalls > before);
    assert.equal(await page.getByText('Selected train refresh failed. Its last report may be stale.', { exact: true }).count(), 1);
    checks.push('refresh retries selected detail and does not erase its error after roster success');

    failDetail = false;
    await page.getByRole('button', { name: 'Retry selected train', exact: true }).click();
    await page.locator('.ops-report-metrics').getByText('Difference', { exact: true }).waitFor();
    assert.equal(await page.getByRole('alert').count(), 0);
    checks.push('detail retry recovers and clears its own error');
    refreshed = true;
    await refresh.click();
    await page.getByRole('heading', { name: `${first.train_name} refreshed`, exact: true }).waitFor();
    checks.push('manual refresh updates the open detail, not just the roster');

    await page.getByRole('button', { name: 'Close train view', exact: true }).click();
    refreshed = false;
    slowFirst = true;
    await page.locator('.overview-train').filter({ hasText: first.train_number }).click();
    await page.locator('.overview-train').filter({ hasText: second.train_number }).click();
    await page.getByRole('heading', { name: second.train_name, exact: true }).waitFor();
    await wait(550);
    assert.equal(await page.locator('.train-focus-panel h2').innerText(), second.train_name);
    checks.push('late response from old selection cannot overwrite the current train');

    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.getByRole('button', { name: 'Close train view', exact: true }).click();
    empty = true;
    await refresh.click();
    await page.getByText('No train records are available yet. Use refresh to check again.', { exact: true }).waitFor();
    checks.push('mobile controller fits viewport; empty roster explains next step');

    await page.goto('http://127.0.0.1:3001/');
    await page.getByText('DEPARTURE DATA NOT AVAILABLE', { exact: true }).waitFor();
    let stationRefreshes = 0;
    page.on('request', request => { if (request.url().includes('/stations/')) ++stationRefreshes; });
    await page.keyboard.press('r');
    await page.waitForResponse(response => response.url().includes('/stations/'));
    assert.ok(stationRefreshes >= 1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    checks.push('station historical empty state and keyboard refresh still work on mobile');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, checks }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
