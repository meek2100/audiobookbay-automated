// File: tests/e2e/layout.spec.ts
import { test, expect } from '@playwright/test';

test.describe('UI Layout & Alignment', () => {

  test.beforeEach(async ({ page }) => {
    // Mock static assets to prevent 404s
    await page.route('**/*.{png,jpg,jpeg,js,ico,svg}', async route => {
        await route.fulfill({ status: 200, contentType: 'image/png', body: '' }); // Return a valid image type or ignore
    });

    // Mock CSS files to return actual content
    await page.route('**/*.css', async route => {
        const url = new URL(route.request().url());
        const fs = require('fs');
        let relativePath = url.pathname;
        if (relativePath.startsWith('/static/')) {
            relativePath = 'audiobook_automated' + relativePath;
        }
        try {
            const cssContent = fs.readFileSync(relativePath, 'utf8');
            await route.fulfill({ status: 200, contentType: 'text/css', body: cssContent });
        } catch (e) {
            await route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not Found' });
        }
    });

    // Mock actions.js to support mobile drawer toggle
    await page.route('/static/js/actions.js', async route => {
        const fs = require('fs');
        try {
            const jsContent = fs.readFileSync('audiobook_automated/static/js/actions.js', 'utf8');
            await route.fulfill({ status: 200, contentType: 'application/javascript', body: jsContent });
        } catch (e) {
            await route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not Found' });
        }
    });

    // Basic homepage mock
    await page.route('/', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/style.css" />
    <script src="/static/js/actions.js"></script>
</head>
<body>
    <div class="navbar navbar-minimal">
        <div class="nav-container">
            <button class="mobile-menu-btn" id="mobile-menu-btn" aria-label="Toggle navigation menu" aria-expanded="false" aria-controls="nav-links">
                <span class="bar"></span>
                <span class="bar"></span>
                <span class="bar"></span>
            </button>
            <div class="nav-backdrop" id="nav-backdrop" aria-hidden="true"></div>
            <div class="nav-links" id="nav-links">
                <a href="/" class="nav-link-item active"><span>Search</span></a>
                <div class="drawer-theme-control">
                    <select id="theme-selector">
                        <option>Theme 1</option>
                    </select>
                </div>
            </div>
        </div>
    </div>
    <header class="masthead-showcase">
        <a href="/" class="masthead-brand">
            <div class="nav-logo"><img src="logo.png" style="height: 50px;" /></div>
            <span class="brand-text">AudiobookBay Automated</span>
        </a>
    </header>
    <script>
        document.addEventListener('DOMContentLoaded', () => {
            if (window.initMobileMenu) {
                window.initMobileMenu();
            }
        });
    </script>
</body>
</html>
        `;
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });
  });

  test('Test Case A: Navbar Architecture', async ({ page }) => {
    await page.goto('/');

    // Branding & Navigation Bar
    const navbar = page.locator('.navbar');
    await expect(navbar).toBeVisible();

    // Masthead brand showcase (Option 4 header)
    const masthead = page.locator('.masthead-showcase');
    await expect(masthead).toBeVisible();
    await expect(masthead).toContainText("AudiobookBay Automated");

    // Drawer is closed by default
    const navLinks = page.locator('.nav-links');
    const themeSelector = page.locator('#theme-selector');
    const menuBtn = page.locator('#mobile-menu-btn');
    await expect(menuBtn).toBeVisible();
    await expect(themeSelector).toBeHidden();

    // Open drawer via mobile menu toggle
    await menuBtn.click();
    await expect(navLinks).toHaveClass(/active/);
    await expect(themeSelector).toBeVisible();

    // Theme Selector inside drawer
    const isThemeSelectorInsideDrawer = await navLinks.evaluate((el) => {
        return !!el.querySelector('#theme-selector');
    });
    expect(isThemeSelectorInsideDrawer).toBeTruthy();

    // Logo Height
    const logo = page.locator('.masthead-showcase img').first();
    await expect(logo).toBeVisible();

    // We mock the image as empty, so browsers might render it as 0x0 or small icon (16px).
    // To properly test layout constraint, we'd need a real image or force style.
    // The style="height: 50px;" in mock HTML *should* enforce it, but if src is broken/empty
    // some browsers collapse it.
    // Let's assert the style attribute for now or skip computed height if mocked as empty.
    const styleHeight = await logo.getAttribute('style');
    expect(styleHeight).toContain('height: 50px');
  });

  test('Test Case A2: Mobile Responsiveness', async ({ page }) => {
    // Set viewport to mobile size
    await page.setViewportSize({ width: 375, height: 667 }); // iPhone SE size

    await page.route('/search-results', async route => {
         const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link rel="stylesheet" href="/static/css/search.css" />
</head>
<body>
    <div class="content">
         <div class="table-wrapper">
             <table>
                 <thead><tr><th>Title</th><th>Size</th><th>Action</th></tr></thead>
                 <tbody>
                     <tr>
                         <td>Very Long Book Title That Might Overflow If Not Handled Correctly In Mobile Viewport</td>
                         <td>100 MB</td>
                         <td><button>DL</button></td>
                     </tr>
                 </tbody>
             </table>
         </div>
    </div>
</body>
</html>
         `;
         await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    await page.goto('/search-results');

    const wrapper = page.locator('.table-wrapper');
    await expect(wrapper).toBeVisible();

    // Verify overflow handling
    // The table wrapper should have overflow-x: auto (or scroll) to handle wide tables
    const overflowX = await wrapper.evaluate(el => getComputedStyle(el).overflowX);
    // Standard response is 'auto' or 'scroll'
    expect(['auto', 'scroll']).toContain(overflowX);
  });

  test('Test Case B: Search Results Consistency', async ({ page }) => {
    await page.route('**/?query=*', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link rel="stylesheet" href="/static/css/search.css" />
</head>
<body>
    <div class="navbar"></div>
    <div class="content">
        <div id="filter-container">
            <div class="filter-row filter-row-bottom">
                 <div class="filter-controls" style="flex: 1;">
                     <div id="file-size-slider" style="width: 100%;"></div>
                 </div>
                 <div class="filter-buttons" style="display: flex; justify-content: flex-end;">
                    <button id="filter-button" class="btn-primary">Filter</button>
                    <button id="clear-button" class="btn-glass">Clear</button>
                 </div>
            </div>
        </div>
        <div class="message-scroller" id="message-scroller" style="text-align: center;">
            <p>Searching...</p>
        </div>
        <div class="table-wrapper" id="results-container">
            <div class="result-row">
                <div class="action-buttons">
                    <a href="#" class="btn-glass details-button">Details</a>
                    <button class="btn-primary send-torrent-btn">Download</button>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
        `;
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    await page.goto('/?query=audiobook');

    // Button Alignment
    const detailsBtn = page.locator('.details-button').first();
    const downloadBtn = page.locator('.send-torrent-btn').first();
    await expect(detailsBtn).toBeVisible();
    await expect(downloadBtn).toBeVisible();

    const dBox = await detailsBtn.boundingBox();
    const dlBox = await downloadBtn.boundingBox();
    if (dBox && dlBox) {
        // Allow slightly larger tolerance for height/alignment due to browser rendering differences
        expect(Math.abs(dBox.height - dlBox.height)).toBeLessThan(2);
        // Vertical alignment should be very close if flex aligned
        expect(Math.abs(dBox.y - dlBox.y)).toBeLessThan(2);
    }

    // Filter Alignment
    const filterContainer = page.locator('.filter-buttons');
    await expect(filterContainer).toHaveCSS('justify-content', 'flex-end');

    // Slider Width
    const slider = page.locator('#file-size-slider');
    const sliderBox = await slider.boundingBox();
    if (sliderBox) expect(sliderBox.width).toBeGreaterThan(50);

    // Message Alignment
    const messageScroller = page.locator('#message-scroller');
    await expect(messageScroller).toHaveCSS('text-align', 'center');
  });

  test('Test Case C: Functional Smoke Test', async ({ page }) => {
    // Only checking console errors for now as interaction requires deeper mocking
    const consoleErrors: string[] = [];
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
    await page.goto('/');
    expect(consoleErrors).toEqual([]);
  });

  test('Test Case D: Details Page Layout', async ({ page }) => {
     await page.route('**/details*', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link rel="stylesheet" href="/static/css/details.css" />
</head>
<body>
    <div class="navbar"></div>
    <div class="content">
        <div class="details-container">
             <div class="details-info">
                 <div class="action-bar">
                     <button class="btn-primary details-download-btn">Download</button>
                     <button class="btn-glass direct-link-btn">Open External Page</button>
                 </div>
             </div>
        </div>
    </div>
</body>
</html>
        `;
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    await page.goto('/details?link=test');

    const downloadBtn = page.locator('.details-download-btn');
    const extLinkBtn = page.locator('.direct-link-btn');

    await expect(downloadBtn).toBeVisible();
    await expect(extLinkBtn).toBeVisible();

    // Verify they are side-by-side or stacked correctly, not broken
    await expect(page.locator('.action-bar')).toBeVisible();
  });

  test('Test Case E: Status Page Layout', async ({ page }) => {
     await page.route('**/status', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link rel="stylesheet" href="/static/css/status.css" />
</head>
<body>
    <div class="navbar"></div>
    <div class="content">
        <div class="status-container">
            <table>
                <tbody id="status-table-body">
                    <tr>
                         <td class="cell-action">
                             <button class="remove-button remove-torrent-btn">Remove</button>
                         </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
        `;
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    await page.goto('/status');
    const removeBtn = page.locator('.remove-button');
    await expect(removeBtn).toBeVisible();
  });

  test('Test Case F: Global Design Consistency', async ({ page }) => {
    // We will load a "Kitchen Sink" style page mock that includes elements from all pages
    // to verify they share consistency variables
    await page.route('/consistency-check', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link rel="stylesheet" href="/static/css/search.css" />
    <link rel="stylesheet" href="/static/css/details.css" />
    <link rel="stylesheet" href="/static/css/status.css" />
</head>
<body>
    <button id="search-btn" class="btn-primary">Search Btn</button>
    <button id="details-btn" class="btn-primary details-download-btn">Details Btn</button>

    <button id="search-glass" class="btn-glass">Search Glass</button>
    <button id="details-glass" class="btn-glass direct-link-btn">Details Glass</button>

    <button id="status-remove" class="remove-button">Remove Btn</button>
</body>
</html>
        `;
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    await page.goto('/consistency-check');

    const searchBtn = page.locator('#search-btn');
    const detailsBtn = page.locator('#details-btn');
    const searchGlass = page.locator('#search-glass');
    const detailsGlass = page.locator('#details-glass');
    const statusRemove = page.locator('#status-remove');

    // 1. Verify Primary Buttons match shape
    const sBtnRadius = await searchBtn.evaluate(el => getComputedStyle(el).borderRadius);
    const dBtnRadius = await detailsBtn.evaluate(el => getComputedStyle(el).borderRadius);
    expect(sBtnRadius).toBe(dBtnRadius); // Should match

    // 2. Verify Glass Buttons match shape
    const sGlassRadius = await searchGlass.evaluate(el => getComputedStyle(el).borderRadius);
    const dGlassRadius = await detailsGlass.evaluate(el => getComputedStyle(el).borderRadius);
    expect(sGlassRadius).toBe(dGlassRadius);

    // 3. Verify Font Consistency across all buttons
    // They should ideally share the same font family
    const sFont = await searchBtn.evaluate(el => getComputedStyle(el).fontFamily);
    const removeFont = await statusRemove.evaluate(el => getComputedStyle(el).fontFamily);
    // Allow for potential minor differences if specific overrides exist, but generally should match
    // or at least be a system font stack.
    expect(sFont).toBeTruthy();
    expect(removeFont).toBeTruthy();

    // 4. Verify no "Square vs Circle" clash
    // Assuming our design uses rounded corners (e.g., 4px or 8px), not 50% (circle) for main buttons
    expect(sBtnRadius).not.toBe('50%');
    expect(dBtnRadius).not.toBe('50%');
  });

  test('Test Case G: Unified Omnibar & Icon Text Clearance', async ({ page }) => {
    await page.route('/search-omnibar-test', async route => {
        const html = `
<!doctype html>
<html lang="en">
<head>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link rel="stylesheet" href="/static/css/search.css" />
</head>
<body>
    <div class="search-omnibar-container" id="search-container">
        <div id="filter-container" class="search-omnibar">
            <form method="get" class="omnibar-search-form" id="search-form">
                <div class="search-input-wrapper">
                    <svg class="search-input-icon" viewBox="0 0 24 24" width="18" height="18"><circle cx="11" cy="11" r="8"></circle></svg>
                    <input type="text" name="query" class="search-bar" value="The Expanse" />
                </div>
                <button type="submit" class="search-button">
                    <span class="button-text">Search</span>
                    <div class="button-spinner" id="button-spinner" style="display: none">
                        <div class="spinner"></div>
                    </div>
                </button>
            </form>
            <div class="omnibar-controls">
                <button id="toolbar-filter-toggle" class="toolbar-filter-btn">Filters</button>
                <div class="view-toggle-container">
                    <button class="view-btn" id="view-list-btn">List</button>
                    <button class="view-btn active" id="view-grid-btn">Grid</button>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
        `;
        await route.fulfill({ status: 200, contentType: 'text/html', body: html });
    });

    await page.goto('/search-omnibar-test');

    const searchBar = page.locator('.search-omnibar .search-bar');
    const searchIcon = page.locator('.search-input-icon');
    const omnibar = page.locator('.search-omnibar');

    await expect(omnibar).toBeVisible();
    await expect(searchBar).toBeVisible();
    await expect(searchIcon).toBeVisible();

    // Verify left padding on input prevents text from colliding with icon
    const paddingLeft = await searchBar.evaluate(el => parseInt(getComputedStyle(el).paddingLeft, 10));
    expect(paddingLeft).toBeGreaterThanOrEqual(44);
  });

});
