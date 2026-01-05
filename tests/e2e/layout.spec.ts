import { test, expect } from '@playwright/test';

test.describe('UI Layout & Alignment', () => {

  test.beforeEach(async ({ page }) => {
    // Mock the homepage or search page to ensure predictable results for layout testing
    await page.route('/', async route => {
        const response = await route.fetch();
        await route.fulfill({ response });
    });
  });

  test('Test Case A: Navbar Architecture', async ({ page }) => {
    await page.goto('/');

    // Branding: Assert that the text "The Crow's Nest" exists within the .navbar container
    const navbar = page.locator('.navbar');
    await expect(navbar).toBeVisible();
    await expect(navbar).toContainText("The Crow's Nest");

    // Theme Selector: Assert that the #theme-selector is the last child (or visually the right-most element)
    // of the .nav-links container.
    const navLinks = page.locator('.nav-links');
    const themeSelector = page.locator('#theme-selector');

    await expect(themeSelector).toBeVisible();

    // Check if it's the last child of nav-links
    const isLastChild = await navLinks.evaluate((el) => {
        const children = el.children;
        const lastChild = children[children.length - 1];
        const themeSelector = document.getElementById('theme-selector');
        return lastChild === themeSelector;
    });

    expect(isLastChild).toBeTruthy();

    // Logo: Assert the logo image has a height greater than 40px
    const logo = navbar.locator('img, .nav-logo img').first();
    await expect(logo).toBeVisible();
    const box = await logo.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
        expect(box.height).toBeGreaterThanOrEqual(40);
    }
  });

  test('Test Case B: Search Results Consistency', async ({ page }) => {
    // Intercept the search request to return a mocked HTML response with results
    // mimicking the structure of search.html
    await page.route('**/?query=*', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Search</title>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link rel="stylesheet" href="/static/css/search.css" />
    <link rel="stylesheet" href="/static/vendor/css/nouislider.min.css" />
</head>
<body>
    <div class="navbar"></div>
    <div class="content">
        <div id="filter-container">
            <div class="filter-row"></div>
            <div class="filter-row filter-row-bottom">
                 <div class="filter-controls">
                     <div class="file-size-filter-wrapper">
                         <label>File Size:</label>
                         <div id="file-size-slider" class="noUi-target noUi-ltr noUi-horizontal"></div>
                     </div>
                 </div>
                 <div class="filter-buttons">
                    <button id="filter-button" class="btn-primary">Filter</button>
                    <button id="clear-button" class="btn-glass">Clear</button>
                 </div>
            </div>
            <div class="view-toggle-row">
                 <div class="view-toggle-container">
                    <button class="view-btn active" id="view-list-btn">List</button>
                    <button class="view-btn" id="view-grid-btn">Grid</button>
                 </div>
            </div>
        </div>

        <div class="message-scroller" id="message-scroller" style="display: block;">
            <p id="scrolling-message">Searching...</p>
        </div>

        <div class="table-wrapper" id="results-container">
            <table>
                <tbody id="results-table-body">
                    <tr class="result-row">
                        <td><img src="cover.jpg" class="cover" /></td>
                        <td>
                            <p class="book-title">Test Book</p>
                        </td>
                        <td>
                            <div class="action-buttons">
                                <a href="#" class="btn-glass details-button">Details</a>
                                <button class="btn-primary send-torrent-btn">Download</button>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
        `;
        await route.fulfill({
            status: 200,
            contentType: 'text/html',
            body: html,
        });
    });

    await page.goto('/?query=audiobook');

    // Wait for CSS to load/apply
    const resultRow = page.locator('.result-row').first();
    await expect(resultRow).toBeVisible();

    // --- Search Button Alignment Check ---
    const actionButtons = resultRow.locator('.action-buttons');
    const detailsBtn = actionButtons.locator('.details-button').first();
    const downloadBtn = actionButtons.locator('.send-torrent-btn').first();

    await expect(detailsBtn).toBeVisible();
    await expect(downloadBtn).toBeVisible();

    const detailsBox = await detailsBtn.boundingBox();
    const downloadBox = await downloadBtn.boundingBox();

    if (detailsBox && downloadBox) {
        expect(Math.abs(detailsBox.height - downloadBox.height)).toBeLessThan(1);
        expect(Math.abs(detailsBox.y - downloadBox.y)).toBeLessThan(1);
    }

    // --- Filter Buttons Alignment Check ---
    const filterContainer = page.locator('.filter-buttons');
    await expect(filterContainer).toBeVisible();
    await expect(filterContainer).toHaveCSS('justify-content', 'flex-end');

    // --- New Check: Slider Visibility & Width ---
    const slider = page.locator('#file-size-slider');
    await expect(slider).toBeVisible();

    const sliderBox = await slider.boundingBox();
    expect(sliderBox).not.toBeNull();
    if (sliderBox) {
        // It should have a significant width, not 0 or collapsed
        expect(sliderBox.width).toBeGreaterThan(50);
    }

    // --- New Check: Filter Controls Flex Growth ---
    const filterControls = page.locator('.filter-controls').first();
    await expect(filterControls).toHaveCSS('flex-grow', '1');

    // --- New Check: Searching Message Alignment ---
    const messageScroller = page.locator('#message-scroller');
    await expect(messageScroller).toBeVisible();
    await expect(messageScroller).toHaveCSS('text-align', 'center');
  });

  test('Test Case C: Functional Smoke Test', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
        }
    });

    await page.goto('/');
    // Check for errors on home page
    expect(consoleErrors).toEqual([]);

    // Check toggles on Search page (mocked)
    await page.route('**/?query=*', async route => {
         const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/search.css" />
</head>
<body>
    <div id="filter-container">
        <div class="view-toggle-row">
            <div class="view-toggle-container">
                <button class="view-btn active" id="view-list-btn">List</button>
                <button class="view-btn" id="view-grid-btn">Grid</button>
            </div>
        </div>
    </div>
    <div class="table-wrapper" id="results-container"></div>
    <script src="/static/js/search.js"></script>
</body>
</html>
        `;
         await route.fulfill({
            status: 200,
            contentType: 'text/html',
            body: html,
        });
    });

    await page.goto('/?query=smoke_test');

    const gridToggle = page.locator('#view-grid-btn');
    const listToggle = page.locator('#view-list-btn');
    const resultsContainer = page.locator('#results-container');

    await expect(gridToggle).toBeVisible();
    await expect(listToggle).toBeVisible();

    // Click Grid
    await gridToggle.click();
    await expect(resultsContainer).toHaveClass(/view-grid/);

    // Click List
    await listToggle.click();
    await expect(resultsContainer).toHaveClass(/view-list/);
  });

});
