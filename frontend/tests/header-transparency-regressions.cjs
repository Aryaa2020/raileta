// Requires the three local Vite apps. No live data is needed for header checks.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.RAILETA_PLAYWRIGHT_PATH || 'playwright');

async function headerStyle(page) {
  return page.locator('.site-nav').evaluate(el => {
    const style = getComputedStyle(el);
    return { background: style.backgroundColor, blur: style.backdropFilter, opacity: style.opacity };
  });
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    await page.goto('http://127.0.0.1:3000/');
    await page.locator('.hero h1').waitFor();
    assert.deepEqual(await headerStyle(page), { background: 'rgba(25, 25, 25, 0.6)', blur: 'blur(4px)', opacity: '1' });
    await page.locator('.hero h1').evaluate(el => window.scrollTo({ top: el.getBoundingClientRect().top + scrollY - 24, behavior: 'instant' }));
    assert.ok((await page.locator('.site-nav').boundingBox()).y <= 8, 'Header stays pinned over scrolling content');
    await page.screenshot({ path: path.resolve('logs/passenger-header-transparency.png') });

    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }] });
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.site-nav')).backdropFilter === 'none');
    assert.deepEqual(await headerStyle(page), { background: 'rgb(16, 16, 16)', blur: 'none', opacity: '1' });
    await cdp.send('Emulation.setEmulatedMedia', { features: [] });
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.site-nav')).backdropFilter === 'blur(4px)');

    await page.setViewportSize({ width: 390, height: 844 });
    const toggle = page.getByRole('button', { name: 'Toggle navigation' });
    await toggle.click();
    assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
    assert.equal(await page.locator('.nav-links').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(23, 20, 29)', 'Mobile menu remains solid for readability');
    await page.getByRole('navigation').getByRole('link', { name: 'Train explorer' }).click();
    assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
    assert.equal((await headerStyle(page)).blur, 'blur(4px)');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

    for (const port of [3001, 3002]) {
      await page.goto(`http://127.0.0.1:${port}/`);
      await page.locator('.site-nav').waitFor();
      const style = await headerStyle(page);
      assert.equal(style.blur, 'none', `Port ${port} stays solid`);
      assert.ok(style.background.startsWith('rgb('), 'Operational header stays fully opaque');
    }
    console.log('PASS: Kiro header opacity/blur, sticky scroll, reduced transparency, mobile menu, and solid operational headers');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
