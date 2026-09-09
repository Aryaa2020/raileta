// Optional end-to-end test against running local services. No external requests.
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('**/*', route => {
    const host = new URL(route.request().url()).hostname;
    return ['127.0.0.1','localhost'].includes(host) ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror',error=>errors.push(error.message));
  try {
    const response = await page.request.get('http://127.0.0.1:8000/api/v1/corridor/MAS-SBC');
    const roster = await response.json();
    assert.equal(roster.dataset_kind,'aggregate_profiles');
    assert.ok(roster.trains.length);
    const number = roster.trains[0].train_number;
    await page.goto('http://127.0.0.1:3000/?profiles=verified');
    await page.getByText('Held-out train profiles',{exact:true}).waitFor();
    await page.getByRole('textbox',{name:'Train number'}).fill(number);
    await page.getByRole('button',{name:'Explore train',exact:true}).click();
    await page.getByText('Past average delay',{exact:true}).waitFor();
    await page.getByText('Past average delay',{exact:true}).scrollIntoViewIfNeeded();
    assert.equal(await page.getByText('Mock expected arrival',{exact:true}).count(),0);
    await page.screenshot({ path:path.resolve('logs/profile-passenger.png'), fullPage:true });
    await page.goto('http://127.0.0.1:3002/');
    await page.locator('.overview-train').filter({hasText:number}).click();
    await page.locator('.ops-report-metrics').getByText('Difference',{exact:true}).waitFor();
    assert.equal(await page.locator('.corridor-track').count(),0);
    await page.screenshot({ path:path.resolve('logs/profile-controller.png'), fullPage:true });
    await page.goto('http://127.0.0.1:3001/');
    await page.getByText('HISTORICAL DELAY PROFILES',{exact:true}).waitFor();
    await page.getByText('DEPARTURE DATA NOT AVAILABLE',{exact:true}).waitFor();
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,train:number,checks:['passenger search -> trained profile','controller selection -> trained profile','no invented map','station unavailable-data label','no browser exceptions']}));
  } finally { await browser.close(); }
})().catch(error=>{ console.error(error);process.exitCode=1; });
