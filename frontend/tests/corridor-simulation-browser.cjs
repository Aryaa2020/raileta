const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    const health=await (await page.request.get('http://127.0.0.1:8000/api/v1/health')).json();
    assert.equal(health.data_mode,'corridor_simulation');
    assert.equal(health.model_version,'mas-sbc-synthetic-v1');
    const report=await (await page.request.get('http://127.0.0.1:8000/api/v1/eta/12027')).json();
    assert.equal(report.journey.mode,'simulation');
    assert.deepEqual(report.journey.stops.map(s=>s.station_code),['MAS','KPD','JTJ','BNC','SBC']);
    assert.ok(report.journey.stops.some(s=>s.forecast?.confidence_lower));
    assert.ok(report.journey.stops.every(s=>s.platform==null));
    for(const width of [1440,390,320]) {
      await page.setViewportSize({width,height:1000});
      await page.goto('http://127.0.0.1:3000/');
      await page.locator('.roster-train').filter({hasText:'12027'}).click();
      await page.getByText('Full timetable & forecast history', {exact:true}).click();
      await page.locator('.report-region .jt-detail').waitFor();
      assert.ok((await page.locator('.report-region .jt-detail').innerText()).includes('SIMULATION ONLY'));
      assert.equal(await page.locator('.report-region .jt-detail > .jt-table-scroll tbody tr').count(),5);
      await page.locator('.report-region').getByRole('button',{name:'Forecast changes',exact:true}).click();
      await page.locator('.report-region').getByRole('img',{name:'Forecast evolution and supplied arrival windows'}).waitFor();
      await page.locator('.report-region').getByRole('button',{name:'Station timeline',exact:true}).click();
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Passenger fits ${width}`);
      if(width===1440) await page.locator('.report-region').screenshot({path:'logs/synthetic-passenger-report.png'});

      await page.goto('http://127.0.0.1:3002/');
      await page.locator('.overview-train').filter({hasText:'12027'}).click();
      await page.locator('.ops-detail-column .jt-detail').waitFor();
      assert.ok((await page.locator('.ops-mode').innerText()).includes('SIMULATION'));
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Controller fits ${width}`);
      if(width===1440) {
        await page.getByText('Journey history, section conditions & accuracy',{exact:true}).click();
        await page.getByRole('button',{name:'Accuracy monitoring',exact:true}).click();
        await page.getByRole('heading',{name:'Active model · mas-sbc-synthetic-v1',exact:true}).waitFor();
        assert.ok((await page.locator('.jt-operational').innerText()).includes('72.2'));
        await page.locator('.jt-operational').screenshot({path:'logs/synthetic-accuracy.png'});
      }
    }
    await page.goto('http://127.0.0.1:3001/');
    await page.getByText('Simulation only',{exact:true}).waitFor({state:'attached'});
    await page.getByRole('button',{name:'Expected arrivals',exact:true}).click();
    await page.getByRole('combobox',{name:'Arrival station'}).selectOption('SBC');
    await page.getByRole('combobox',{name:'Arrival time window'}).selectOption('24');
    assert.equal(await page.getByRole('combobox',{name:'Journey data source'}).inputValue(),'simulation');
    await page.waitForFunction(()=>!document.querySelector('.jt-arrivals [role="status"]'));
    assert.ok((await page.locator('.jt-arrivals').innerText()).includes('Synthetic arrivals only'));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);
    console.log('PASS: trained simulation API, real stopping pattern, no invented platforms, passenger/controller desktop+mobile, forecast history, accuracy/stress disclosure, arrivals mode');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
