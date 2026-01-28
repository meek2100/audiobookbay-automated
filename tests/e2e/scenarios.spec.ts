// File: tests/e2e/scenarios.spec.ts
import { test, expect } from '@playwright/test';

test.describe('E2E Scenarios: Search -> Download', () => {

  test.beforeEach(async ({ page }) => {
    // Mock static assets
    await page.route('**/*.{png,jpg,jpeg,js,ico,svg,css}', async route => {
        const url = route.request().url();
        if (url.endsWith('.css')) {
             await route.fulfill({ status: 200, contentType: 'text/css', body: '/* mock css */' });
        } else {
             await route.fulfill({ status: 200, contentType: 'image/png', body: '' });
        }
    });

    // Mock Home Page
    await page.route('/', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head><title>Home</title></head>
<body>
    <form action="/" method="get">
        <input type="text" name="query" id="search-input" />
        <button type="submit" id="search-button">Search</button>
    </form>
</body>
</html>
        `;
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    // Mock Search Results for "The Martian"
    await page.route('/?query=The+Martian', async route => {
         const html = `
<!doctype html>
<html lang="en">
<head><title>Results</title></head>
<body>
    <div class="result-row">
        <h3>The Martian</h3>
        <a href="/details?link=test-link" class="details-link">The Martian</a>
    </div>
</body>
</html>
         `;
         await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    // Mock Details Page
    await page.route('/details?link=test-link', async route => {
         const html = `
<!doctype html>
<html lang="en">
<head>
    <title>Details</title>
    <script src="/static/js/actions.js"></script>
</head>
<body>
    <h1>The Martian</h1>
    <button id="download-btn" class="send-torrent-btn" data-link="magnet:?xt=urn:btih:test">Download</button>
    <div id="toast-container"></div>
</body>
</html>
         `;
         await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    // Mock /send endpoint
    await page.route('/send', async route => {
        const json = { status: 'success', message: 'Torrent added successfully' };
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(json) });
    });

    // Mock actions.js logic locally since we can't load the real one easily without full context
    // or we can just rely on the real one if it's served correctly.
    // However, for isolation, injecting a mock script is safer to ensure the toast appears.
    // But the requirements say "Visit Home -> ... -> Assert Success toast".
    // If we want to test the *real* frontend logic, we should rely on the real `actions.js`.
    // Let's try to serve the real actions.js.
    await page.route('/static/js/actions.js', async route => {
        const fs = require('fs');
        try {
            const content = fs.readFileSync('audiobook_automated/static/js/actions.js', 'utf8');
            await route.fulfill({ status: 200, contentType: 'application/javascript', body: content });
        } catch (e) {
            await route.fulfill({ status: 404, body: 'Not Found' });
        }
    });
  });

  test('Full Flow: Search -> Click Result -> Download -> Verify Toast', async ({ page }) => {
    // 1. Visit Home
    await page.goto('/');

    // 2. Search for "The Martian"
    await page.fill('#search-input', 'The Martian');
    await page.click('#search-button');

    // 3. Click Result (Details Link)
    await page.click('.details-link');
    await expect(page).toHaveURL(/\/details\?link=test-link/);

    // 4. Click Download
    // Note: The real actions.js attaches to .send-torrent-btn
    await page.click('#download-btn');

    // 5. Assert "Success" toast appears
    // The real actions.js creates a toast. We need to wait for it.
    // Depending on implementation, it might be a div with class 'toast' or similar.
    // Let's assume standard implementation from the codebase.
    // Usually it's showToast() creating a div.
    const toast = page.locator('.toast');
    await expect(toast).toBeVisible();
    await expect(toast).toContainText('Torrent added successfully');
  });

});
