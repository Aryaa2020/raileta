const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/v1/corridor/**', route => route.fulfill({ json: { data_mode: 'historical_replay', trains: [] } }));
    await page.goto('http://127.0.0.1:3000/');
    const sleepers = page.locator('.hero-track-sweep .hero-track-sleepers path');
    assert.ok(await sleepers.count() > 30);
    const delays = await sleepers.evaluateAll(elements => elements.map(el => parseFloat(getComputedStyle(el).animationDelay)));
    assert.ok(delays.every((delay, i) => i === 0 || delay > delays[i - 1]), 'Sleepers appear sequentially');
    assert.equal(await sleepers.first().evaluate(el => getComputedStyle(el).animationDuration), '0.54s');
    assert.equal(await sleepers.first().evaluate(el => getComputedStyle(el).animationIterationCount), '1');
    await page.waitForFunction(() => [...document.querySelectorAll('.hero-track-sweep path')].every(el => getComputedStyle(el).opacity === '1'));
    const startTime = await sleepers.first().evaluate(el => el.getAnimations()[0].startTime);
    await page.getByRole('button', { name: 'Refresh train list' }).click();
    assert.equal(await sleepers.first().evaluate(el => el.getAnimations()[0].startTime), startTime, 'Data refresh does not replay the decoration');

    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const width of [1920, 1440, 1110, 1100, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      const track = page.locator(width > 1100 ? '.hero-track-sweep' : '.hero-track-compact');
      assert.ok(await track.isVisible());
      assert.equal(await track.getAttribute('aria-hidden'), 'true');
      assert.equal(await track.evaluate(el => getComputedStyle(el).pointerEvents), 'none');
      assert.equal(await track.locator('path').first().evaluate(el => getComputedStyle(el).animationName), 'none');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No overflow at ${width}px`);
      const edges = await track.evaluate(svg => {
        const rect = svg.getBoundingClientRect();
        const rails = [...svg.querySelectorAll('.hero-track-rails path')].map(rail => {
          const matrix = rail.getScreenCTM();
          const start = rail.getPointAtLength(0).matrixTransform(matrix);
          const end = rail.getPointAtLength(rail.getTotalLength()).matrixTransform(matrix);
          return { startX: start.x, endX: end.x, startY: start.y, endY: end.y };
        });
        return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: document.documentElement.clientWidth, rails };
      });
      assert.ok(Math.abs(edges.left) < 1 && Math.abs(edges.right - edges.width) < 1, 'Decoration spans the available screen width');
      for (const rail of edges.rails) {
        assert.ok(rail.startX < 0 && rail.endX > edges.width, 'Both rails continue beyond both screen edges');
        assert.ok(rail.startY > edges.top && rail.startY < edges.bottom && rail.endY > edges.top && rail.endY < edges.bottom, 'Both rail ends cross the visible side edges');
      }
      assert.equal(await track.evaluate(el => getComputedStyle(el).zIndex), '-1', 'Track paints behind the text');
      assert.notEqual(await page.locator('.hero-copy').evaluate(el => getComputedStyle(el).textShadow), 'none', 'Text retains a dark contrast halo over the track');
      if ([1440, 390].includes(width)) await page.screenshot({ path: `logs/hero-track-${width}.png` });
    }
    await page.goto('http://127.0.0.1:3002/');
    assert.equal(await page.locator('.hero-track').count(), 0, 'Controller has no decorative hero track');
    assert.deepEqual(errors, []);
    console.log('PASS: sequential reveal, no refresh replay, reduced motion, seven edge-to-edge responsive sizes, readable text layering, controller unchanged');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
