const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');
const reference = require('../../data/reference/chennai_bengaluru.json');

(async () => {
  const { matchingTrains } = await import('../shared/trainSearch.mjs');
  const trains = reference.trains.map(train => ({ train_number: train.number, train_name: train.name, stops: train.stops.map(([code]) => ({ station_code: code, station_name: reference.stations[code][0] })) }));
  for (const query of ['shatabdi', '12027', '1202', 'CHENNAI TO BLR', 'MAS → SBC', 'katpadi', 'bangalore']) assert.ok(matchingTrains(trains, query).some(t => t.train_number === '12027'), query);
  for (const query of ['Bangalore to Chennai', 'SBC → MAS', 'nonexistent', '   ']) assert.equal(matchingTrains(trains, query).length, 0, query);
  assert.deepEqual(matchingTrains(trains, 'Perambur').map(t => t.train_number), ['12607']);
  assert.deepEqual(matchingTrains(trains, 'AB').map(t => t.train_number), ['12607', '12639']);
  assert.equal(matchingTrains(trains, 'Bangalore-Chennai').length, 0);
  assert.equal(matchingTrains(trains, trains[0].train_name)[0].train_number, '12027');
  assert.equal(matchingTrains(trains, '12657 mail')[0].train_number, '12657');
  const stops = trains[0].stops.map((stop, i) => ({ ...stop, sequence: i, scheduled_arrival: i ? `2026-01-15T${13 + i}:00:00Z` : null, scheduled_departure: i === 4 ? null : `2026-01-15T${13 + i}:02:00Z`, actual_arrival: i === 1 ? '2026-01-15T14:05:00Z' : null, actual_departure: i === 0 ? '2026-01-15T13:05:00Z' : null, forecast: i > 1 ? { predicted_arrival: '2026-01-15T19:10:00Z', confidence_lower: '2026-01-15T19:00:00Z', confidence_upper: '2026-01-15T19:20:00Z', reasons: [], model_version: 'test' } : null }));
  let journey = { id: 'fixture', train_number: '12027', train_name: trains[0].train_name, start_date: '2026-01-15', mode: 'simulation', scenario_time: '2026-01-15T14:06:00Z', status: 'running', is_stale: false, last_reported_time: '2026-01-15T14:05:00Z', stops, next_stop: stops[2], conditions: [] };
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ reducedMotion: 'reduce' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      const json = path.includes('/corridor/') ? { data_mode: 'corridor_simulation', trains, scenario_date: '2026-01-15' } : path.includes('/eta/') ? { train_number: '12027', data_mode: 'corridor_simulation', journey } : { journeys: [] };
      await route.fulfill({ json });
    });
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(process.env.RAILETA_PASSENGER_URL || 'http://127.0.0.1:3000');
      const search = page.getByRole('textbox', { name: 'Search trains' });
      await search.fill('Chennai to Bangalore');
      await page.getByRole('region', { name: 'Matching trains' }).getByRole('button').nth(3).waitFor();
      await search.fill('Shatabdi');
      await search.press('Enter');
      await page.locator('.pj-arrival-time').waitFor();
      await page.waitForFunction(() => {
        const panel = document.querySelector('.pj-layout');
        const nav = document.querySelector('.site-nav');
        return panel === document.activeElement && Math.abs(panel.getBoundingClientRect().top - nav.getBoundingClientRect().bottom - 20) < 3;
      });
      assert.ok(await page.evaluate(() => document.fonts.check('400 16px Ubuntu') && getComputedStyle(document.querySelector('.pj-arrival-time')).fontFamily.startsWith('Ubuntu')), 'Ubuntu is loaded and applied');
      assert.match(await page.locator('.pj-arrival-time').innerText(), /12:40 am/i);
      assert.match(await page.locator('.pj-arrival-result').innerText(), /16 Jan 2026/);
      assert.equal(await page.locator('.pj-route li').count(), 5);
      assert.equal(await page.locator('.pj-route .is-last-report').count(), 1);
      assert.match(await page.locator('.pj-route .is-last-report').innerText(), /Katpadi/);
      await page.getByRole('combobox', { name: 'Your arrival station' }).selectOption('1');
      assert.match(await page.locator('.pj-arrival-result').innerText(), /Arrived at/);
      assert.equal(await page.locator('.pj-window').count(), 0, 'Actual arrival supersedes forecasts');
      await page.locator('.pj-route li').last().getByRole('button').click();
      assert.equal(await page.getByRole('combobox', { name: 'Your arrival station' }).inputValue(), '4');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Fits ${width}px`);
      if (width === 1440) await page.locator('.passenger-journey').screenshot({ path: 'logs/passenger-arrival-desktop.png' });
      if (width === 390) await page.locator('.passenger-journey').screenshot({ path: 'logs/passenger-arrival-mobile.png' });
    }
    journey = { ...journey, is_stale: true };
    await page.reload();
    await page.locator('.roster-train').filter({ hasText: '12027' }).click();
    await page.getByText('Last arrival estimate', { exact: true }).waitFor();
    assert.match(await page.locator('.pj-stale').innerText(), /Waiting for a newer report/);
    journey = { ...journey, stops: stops.map(s => ({ ...s, forecast: null })) };
    await page.reload();
    await page.locator('.roster-train').filter({ hasText: '12027' }).click();
    await page.getByText('Waiting for an arrival estimate', { exact: true }).waitFor();
    assert.equal(await page.locator('.pj-arrival-time').innerText(), 'Not available yet');
    assert.deepEqual(errors, []);
    console.log('PASS: name/number/station/ordered-route search, arrival selection, overnight IST dates, reported-stop marker, stale/missing forecasts and responsive layouts');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
