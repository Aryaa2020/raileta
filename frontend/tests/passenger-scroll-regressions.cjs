const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

// isVisible()/locator.click() can pass for an off-screen search: Playwright
// scrolls it back into view. Check screen coordinates and hit targets instead.
async function assertSearchOnScreen(page) {
  const state = await page.evaluate(() => {
    const panel = document.querySelector('.search-panel').getBoundingClientRect();
    const controls = [...document.querySelectorAll('.search-panel input, .search-panel button')].map(element => {
      const rect = element.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return { label: element.getAttribute('aria-label') || element.textContent, top: rect.top, bottom: rect.bottom, reachable: hit === element || element.contains(hit) };
    });
    return { top: panel.top, bottom: panel.bottom, viewport: innerHeight, controls };
  });
  assert.ok(state.top >= 16, `Search panel is clipped above the screen: ${JSON.stringify(state)}`);
  assert.ok(state.bottom <= state.viewport - 16, 'The full search panel must fit in the screen');
  for (const control of state.controls) assert.ok(control.reachable, `${control.label} must be directly reachable, without auto-scrolling`);
}

async function physicalClick(page, selector) {
  const point = await page.locator(selector).first().evaluate(element => {
    const rect = element.getBoundingClientRect();
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  });
  await page.mouse.click(point.x, point.y);
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  try {
    for (const viewport of [{width:1366,height:768},{width:1440,height:1000},{width:1920,height:1440},{width:390,height:844},{width:320,height:568},{width:844,height:390}]) {
      const page = await browser.newPage({ viewport });
      const errors = [];
      page.on('pageerror', error=>errors.push(error.message));
      await page.goto('http://127.0.0.1:4173/?scroll-regression=1');
      await page.getByText('Held-out train profiles',{exact:true}).waitFor();
      // Real wheel input, no click/focus/scrollIntoView to accidentally complete
      // an otherwise unreachable transition.
      await page.mouse.move(viewport.width/2,viewport.height/2);
      for(let i=0;i<8;i++) await page.mouse.wheel(0,300);
      await page.waitForFunction(()=>window.scrollY>0);
      const state = await page.evaluate(()=>({
        viewport:innerHeight, scroll:scrollY, maxScroll:document.documentElement.scrollHeight-innerHeight,
        required:document.querySelector('.scroll-scene').offsetHeight-document.querySelector('.scene-viewport').clientHeight,
        phase:document.querySelector('#top').className, opacity:getComputedStyle(document.querySelector('.dashboard-layer')).opacity,
      }));
      console.log(JSON.stringify({viewport,...state}));
      if(!process.argv.includes('--probe')) {
        await page.waitForFunction(()=>document.querySelector('#top').classList.contains('journey-stage-dashboard'));
        assert.ok(Math.abs(state.maxScroll-state.required) <= 1,'The page must stop at the handoff, without extra footer/padding scroll');
        // Finish the wheel gesture before reversing it; pending wheel events
        // otherwise race a synthetic Home key in Chromium.
        await page.waitForTimeout(300);
        await assertSearchOnScreen(page);
        await page.setViewportSize({width:viewport.width,height:viewport.height+180});
        await page.waitForTimeout(200);
        await assertSearchOnScreen(page);
        assert.equal(await page.locator('.dashboard-layer').getAttribute('inert'),null,'Resizing the window must not hide/disable the reached search');
        await page.setViewportSize(viewport);
        await page.waitForTimeout(200);
        await assertSearchOnScreen(page);
        // Continuing a strong downward gesture must not hide the input. On
        // small screens, only the reports pane scrolls to reveal the last card.
        const pane = await page.locator('.dashboard-content').boundingBox();
        await page.mouse.move(pane.x + pane.width / 2, pane.y + pane.height / 2);
        await page.mouse.wheel(0,3000);
        await page.waitForTimeout(300);
        await assertSearchOnScreen(page);
        const lastCard = await page.locator('.delayed-train').last().boundingBox();
        assert.ok(lastCard.y >= pane.y - 1 && lastCard.y + lastCard.height <= pane.y + pane.height + 1,'The last train must be reachable within the reports pane');
        // Reverse the nested list first, then the document, just like native
        // scroll chaining. No wheel handler should trap the user in either.
        await page.mouse.wheel(0,-3000);
        await page.waitForTimeout(300);
        await page.mouse.wheel(0,-3000);
        await page.waitForFunction(()=>window.scrollY===0,null,{timeout:5000});
        await page.waitForFunction(()=>document.querySelector('#top').classList.contains('journey-stage-cover'));
        // Keyboard-only completion must also work.
        for(let i=0;i<3;i++) {
          await page.keyboard.press('PageDown');
          // Browser-native keyboard scrolling animates; space physical inputs
          // rather than coalescing three commands into the Home animation.
          await page.waitForTimeout(250);
        }
        console.log('keyboard',await page.evaluate(()=>({y:scrollY,phase:document.querySelector('#top').className,focus:document.activeElement.tagName})));
        await page.waitForFunction(()=>document.querySelector('#top').classList.contains('journey-stage-dashboard'),null,{timeout:5000});
        await page.waitForTimeout(300);
        await assertSearchOnScreen(page);
        await page.screenshot({path:`logs/passenger-landing-${viewport.width}x${viewport.height}.png`});
        const searchTop = await page.locator('.search-panel').evaluate(element=>element.getBoundingClientRect().top);
        if (viewport.width === 1366) {
          const train = await page.locator('.quick-train').first().evaluate(element=>element.firstChild.textContent);
          await physicalClick(page, 'input[aria-label="Train number"]');
          await page.keyboard.type(train);
          await physicalClick(page, '.track-button');
        } else {
          await physicalClick(page, '.quick-train');
        }
        await page.getByText('Recorded average delay',{exact:true}).waitFor();
        await assertSearchOnScreen(page);
        const lockedTop = await page.locator('.search-panel').evaluate(element=>element.getBoundingClientRect().top);
        assert.ok(Math.abs(searchTop-lockedTop) <= 1,'Selecting a train must preserve the search position');
        await page.keyboard.press('Control+Home');
        await page.waitForFunction(()=>Number(getComputedStyle(document.querySelector('.dashboard-layer')).opacity)>.99);
        assert.equal(await page.locator('.cover-layer').isVisible(),false,'A selected train must not restore the cover');
        await page.getByRole('button',{name:'Back to trains',exact:true}).click();
        await page.getByRole('heading',{name:'Held-out train profiles',exact:true}).waitFor();
        assert.equal(await page.locator('.cover-layer').isVisible(),false,'Back to trains must not unlock the cover');
        await page.setViewportSize({width:viewport.width,height:Math.max(500,viewport.height-120)});
        await page.keyboard.press('Control+Home');
        assert.equal(await page.locator('.cover-layer').isVisible(),false,'Resize must not recreate a scroll trap');
        assert.deepEqual(errors,[]);
      }
      await page.close();
    }
    if(!process.argv.includes('--probe')) {
      for(const mode of ['empty','error']) {
        const page = await browser.newPage({viewport:{width:1920,height:1440},reducedMotion:'reduce'});
        await page.route('**/api/v1/corridor/**',route=>route.fulfill(mode==='error'
          ? {status:503,json:{detail:'Test-only backend unavailable'}}
          : {json:{data_mode:'historical_replay',trains:[],total_trains:0}}));
        await page.goto('http://127.0.0.1:4173/');
        assert.equal(await page.getByRole('textbox',{name:'Train number'}).count(),0,'Invisible search must not take keyboard focus on the cover');
        await page.mouse.wheel(0,2400);
        await page.waitForFunction(()=>document.querySelector('#top').classList.contains('journey-stage-dashboard'));
        if(mode==='error') await page.getByRole('alert').waitFor();
        else await page.getByText('No train records have been received yet.',{exact:true}).waitFor();
        assert.equal(await page.getByRole('textbox',{name:'Train number'}).isVisible(),true);
        await page.waitForTimeout(300);
        await assertSearchOnScreen(page);
        await page.mouse.wheel(0,-3000);
        await page.waitForFunction(()=>document.querySelector('#top').classList.contains('journey-stage-cover'));
        await page.close();
      }
      console.log('Passenger regression checks passed: six screen sizes, bounded landing, directly clickable search/examples, scrollable full roster, reverse, keyboard, locked selection/back/resize, empty/error and reduced motion.');
    }
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
