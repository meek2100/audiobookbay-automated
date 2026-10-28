// File: tests/e2e/capture_screenshots.js
const { chromium } = require('@playwright/test');
const path = require('path');

(async () => {
    const browser = await chromium.launch({
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2 // 1440 * 2 = 2880px wide Retina high-res screenshot
    });

    const page = await context.newPage();

    // Set sessionStorage & localStorage to ensure splash is disabled in browser context as well
    await page.addInitScript(() => {
        sessionStorage.setItem('splashShown', 'true');
        localStorage.setItem('splashShown', 'true');
        document.documentElement.classList.add('no-splash');
    });

    // 1. Capture Search Results Page
    console.log('Capturing Search page with results...');
    await page.goto('http://127.0.0.1:5078/?query=dune', { waitUntil: 'domcontentloaded' });
    // Wait for book cards / table to render cleanly
    await page.waitForSelector('.book-row, .book-card', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(__dirname, '../../docs/images/search.png') });
    console.log('Saved docs/images/search.png');

    // 2. Capture Details Page
    console.log('Capturing Details page...');
    await page.goto('http://127.0.0.1:5078/details?link=/abss/dune-frank-herbert-2/', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.book-details-container, .desc', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(__dirname, '../../docs/images/details.png') });
    console.log('Saved docs/images/details.png');

    // 3. Capture Status Page
    console.log('Capturing Status page...');
    await page.goto('http://127.0.0.1:5078/status', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.status-client-pill, table', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(__dirname, '../../docs/images/status.png') });
    console.log('Saved docs/images/status.png');

    await browser.close();
    console.log('All screenshots captured successfully!');
})();
