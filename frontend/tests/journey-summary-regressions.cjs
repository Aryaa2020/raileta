// Run with the passenger app on :3000 and historical backend on :8000.
// Event fixtures are test-only. They never modify the dataset or production API.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const checks = [];
  const errors = [];
  try {
    const context = await browser.newContext({ reducedMotion: 'reduce', viewport: { width: 1440, height: 1000 } });
    await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const real = await (await page.request.get('http://127.0.0.1:8000/api/v1/eta/16127')).json();
    assert.equal(real.dataset_kind, 'aggregate_profiles');
    let fixture = real;
    await page.route('**/api/v1/eta/**', route => route.fulfill({ json: fixture }));
    await page.route('**/api/v1/corridor/**', route => route.fulfill({ json: { data_mode: 'simulated', trains: [] } }));
    const select = async () => {
      await page.goto('http://127.0.0.1:3000/');
      await page.getByRole('textbox', { name: 'Train number' }).fill('16127');
      await page.getByRole('textbox', { name: 'Train number' }).press('Enter');
      await page.locator('.journey-progress').waitFor();
    };
    const layout = async () => assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal page overflow');
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await select();
      assert.deepEqual(await page.locator('.simple-delay-metrics dt').allTextContents(), ['Past average delay', 'RailETA estimate', 'Difference']);
      const format = value => new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(value) + ' min';
      const record = real.historical_replay;
      assert.deepEqual(await page.locator('.simple-delay-metrics dd').allTextContents(), [record.recorded_average_delay_minutes, record.predicted_average_delay_minutes, record.absolute_error_minutes].map(format));
      assert.equal(await page.locator('.report-details').getAttribute('open'), null);
      assert.equal(await page.getByRole('progressbar').count(), 0, 'Historical data must not invent a completed percentage');
      assert.equal(await page.locator('.journey-progress-value').innerText(), 'Not live');
      assert.equal(await page.locator('.journey-placeholder i').count(), 3);
      await layout();
      if ([1440, 390].includes(width)) await page.locator('.simple-report').screenshot({ path: path.resolve(`logs/simple-summary-${width}.png`) });
      await page.locator('.report-details>summary').focus();
      await page.keyboard.press('Enter');
      await page.getByRole('heading', { name: 'How reliable is it?' }).waitFor();
      await layout();
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('.report-details').getAttribute('open'), null);
      checks.push(`Historical summary at ${width}px: plain labels, accurate numbers, unknown progress, keyboard disclosure, no overflow`);
    }
    const stops = [
      { station_code: 'MAS', station_name: 'Chennai Central' },
      { station_code: 'KPD', station_name: 'Katpadi Junction' },
      { station_code: 'SBC', station_name: 'KSR Bengaluru' },
    ];
    const event = {
      train_number: '16127', train_name: 'Journey test service', train_class: 'Express', data_mode: 'simulated',
      route_stops: stops, route_geometry: null, upcoming_stations: [], overall_delay_reasons: [],
      current_status: { last_reported_station: 'KPD', last_reported_time: '2026-09-09T06:00:00Z', current_delay_minutes: 12 },
    };
    await page.setViewportSize({ width: 1100, height: 900 });
    for (const [index, percent] of [[0, 0], [1, 50], [2, 100]]) {
      fixture = { ...event, current_status: { ...event.current_status, last_reported_station: stops[index].station_code } };
      await select();
      assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'), String(percent));
      assert.equal(await page.locator('.journey-stations .is-reached').count(), index + 1);
      assert.equal(await page.locator('.journey-stations [aria-current="step"] strong').innerText(), stops[index].station_name);
      assert.ok((await page.locator('.journey-progress-note').innerText()).includes('not distance or time'));
      assert.ok((await page.locator('.journey-progress-note').innerText()).includes('Demo station updates'));
      await layout();
      if (index === 1) await page.locator('.journey-progress').screenshot({ path: path.resolve('logs/journey-progress-demo.png') });
    }
    checks.push('Event reports: 0%, 50%, 100%, reached markers, current station, explicit stop-based demo labels');
    fixture = { ...event, is_stale: true };
    await select();
    assert.ok((await page.locator('.journey-progress-note').innerText()).includes('This report is old; the train may have moved.'));
    checks.push('Old station reports explicitly marked stale');
    for (const unavailable of [
      { ...event, route_stops: [] },
      { ...event, route_stops: [stops[0]] },
      { ...event, current_status: {} },
      { ...event, current_status: { last_reported_station: 'UNKNOWN' } },
      { ...event, route_stops: [...stops, stops[1]] },
      { ...real, route_stops: stops, current_status: event.current_status },
    ]) {
      fixture = unavailable;
      await select();
      assert.equal(await page.getByRole('progressbar').count(), 0);
      assert.equal(await page.locator('.journey-placeholder i').count(), 3);
    }
    checks.push('Missing, insufficient, ambiguous, and historical station data never fabricates progress');
    fixture = { ...event, route_stops: Array.from({ length: 20 }, (_, index) => ({ station_code: `ST${index}`, station_name: `Station ${index}` })), current_status: { last_reported_station: 'ST12' } };
    await page.setViewportSize({ width: 320, height: 800 });
    await select();
    await layout();
    assert.ok(await page.locator('.journey-stations-scroller').evaluate(el => el.scrollWidth > el.clientWidth), 'Long routes scroll inside the card');
    checks.push('20-stop route scrolls within the card on 320px mobile');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, checks }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
