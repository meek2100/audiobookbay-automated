// File: tests/js/search.test.js
/**
 * @jest-environment jsdom
 */

// NOTE: searchJsContent is available globally from jest.setup.js

// Function to extract the global functions that were exposed by search.js
const getGlobalFunctions = () => {
    // The functions are explicitly attached to window in the source file.
    return {
        parseFileSizeToMB: window.parseFileSizeToMB,
        formatFileSize: window.formatFileSize,
        initializeFilters: window.initializeFilters,
        applyFilters: window.applyFilters,
        clearFilters: window.clearFilters,
        showLoadingSpinner: window.showLoadingSpinner,
        hideLoadingSpinner: window.hideLoadingSpinner,
        setViewMode: window.setViewMode,
        initFloatingHud: window.initFloatingHud,
        initTopFilterDrawer: window.initTopFilterDrawer,
        syncHudFilters: window.syncHudFilters,
        streamRemainingPages: window.streamRemainingPages,
        createResultRowElement: window.createResultRowElement,
        initHoverPrefetch: window.initHoverPrefetch,
        initInfiniteScroll: window.initInfiniteScroll,
        loadNextPage: window.loadNextPage,
        resetPaginationState: window.resetPaginationState,
    };
};

// Helper to create a mock result row for filter tests
const createResultRow = (category, language, bitrate, size, date, format = "MP3", display = "") => {
    const row = document.createElement("tr");
    row.className = "result-row";
    row.dataset.category = category;
    row.dataset.language = language;
    row.dataset.bitrate = bitrate;
    row.dataset.fileSize = size;
    row.dataset.postDate = date;
    row.dataset.format = format;
    row.style.display = display;
    return row;
};

// --- CORE SETUP HELPER (Defined at top-level scope for universal access) ---
// This function runs the DOM-heavy setup for the Filter Logic block.
const setup = () => {
    // Clear DOM before each test
    document.body.innerHTML = "";

    // Setup Filter Controls (native date and size dropdowns)
    document.body.innerHTML = `
        <div id="search-container">
            <button class="search-button">
                <span class="button-text">Search</span>
                <div id="button-spinner" style="display: none"></div>
            </button>
        </div>
        <div id="message-scroller" style="display: none">
            <p id="scrolling-message"></p>
        </div>
        <div id="filter-container">
            <select id="category-filter">
                <option value="">All Categories</option>
                <option value="Fiction">Fiction</option>
                <option value="Non-Fiction">Non-Fiction</option>
                <option value="Science">Science</option>
            </select>
            <select id="language-filter">
                <option value="">All Languages</option>
                <option value="English">English</option>
                <option value="Spanish">Spanish</option>
            </select>
            <select id="bitrate-filter">
                <option value="">All Bitrates</option>
                <option value="64 Kbps">64 Kbps</option>
                <option value="128 Kbps">128 Kbps</option>
            </select>
            <select id="format-filter">
                <option value="">All Formats</option>
                <option value="M4B">M4B</option>
                <option value="MP3">MP3</option>
            </select>
            <select id="file-size-filter">
                <option value="">Any Size</option>
                <option value="under_500mb">&lt; 500 MB</option>
                <option value="500mb_2gb">500 MB – 2 GB</option>
                <option value="2gb_5gb">2 GB – 5 GB</option>
                <option value="over_5gb">&gt; 5 GB</option>
            </select>
            <input type="date" id="date-from-filter" />
            <input type="date" id="date-to-filter" />
            <div class="filter-buttons"><button id="filter-button"></button><button id="clear-button"></button></div>
        </div>
        <table><tbody id="results-table-body"></tbody></table>
    `;

    // Add mock result rows to the DOM
    const tbody = document.getElementById("results-table-body");
    // Changed category to a compound name to test the new split logic (pipe delimiter)
    tbody.appendChild(createResultRow("Fiction|Science", "English", "128 Kbps", "500 MB", "01 Jan 2024", "M4B"));
    tbody.appendChild(createResultRow("Non-Fiction", "Spanish", "64 Kbps", "1.5 GB", "15 Feb 2024", "MP3"));
    tbody.appendChild(createResultRow("Fiction", "English", "128 Kbps", "100 MB", "20 Dec 2023", "M4B"));
    tbody.appendChild(createResultRow("Fiction", "English", "Unknown", "10 GB", "Unknown", "MP3")); // Max size row: 10240 MB
    tbody.appendChild(createResultRow("Unknown", "Unknown", "Unknown", "Unknown", "Unknown", "Unknown")); // Fully Unknown row

    const functions = getGlobalFunctions();
    if (functions.resetPaginationState) {
        functions.resetPaginationState();
    }
    functions.initializeFilters();

    // Manually trigger DOMContentLoaded to run initializeFilters setup
    document.dispatchEvent(new Event("DOMContentLoaded"));

    return {
        functions,
        mockFilter: (id, value) => {
            document.getElementById(id).value = value;
        },
        mockApply: functions.applyFilters,
        mockClear: functions.clearFilters,
    };
};

// Helper functions for mock application (defined universally)
const mockFilter = (id, value) => {
    document.getElementById(id).value = value;
};

// --- START TESTS ---

describe("search.js Unit Tests - File Size Utilities", () => {
    // CRITICAL: Run the evaluation once here to make file size functions available for all tests in this suite.
    beforeAll(() => {
        eval(global.searchJsContent);
    });

    // NOTE: These tests rely only on the global functions being defined, not the DOM setup.

    test("should return correct MB for GB", () => {
        const { parseFileSizeToMB } = getGlobalFunctions();
        expect(parseFileSizeToMB("1.5 GB")).toBe(1536); // 1.5 * 1024
    });

    test("should return correct MB for TB", () => {
        const { parseFileSizeToMB } = getGlobalFunctions();
        expect(parseFileSizeToMB("1 TB")).toBe(1048576); // 1 * 1024 * 1024
    });

    test("should handle KB (less than 1 MB)", () => {
        const { parseFileSizeToMB } = getGlobalFunctions();
        expect(parseFileSizeToMB("500 KB")).toBeCloseTo(0.48828125); // 500 / 1024
    });

    test("should handle Bytes, Megabytes, and Petabytes", () => {
        const { parseFileSizeToMB } = getGlobalFunctions();

        // Bytes (B)
        expect(parseFileSizeToMB("500 B")).toBeCloseTo(500 / (1024 * 1024));

        // Megabytes (MB) - The input usually comes as "MB" or "MBs"
        expect(parseFileSizeToMB("500 MB")).toBe(500);

        // Petabytes (PB)
        expect(parseFileSizeToMB("1 PB")).toBe(1024 * 1024 * 1024);
    });

    test("should return null for Unknown or empty string", () => {
        const { parseFileSizeToMB } = getGlobalFunctions();
        expect(parseFileSizeToMB("Unknown")).toBeNull();
    });

    test("should warn and return raw number for unrecognized units", () => {
        const consoleSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
        const { parseFileSizeToMB } = getGlobalFunctions();
        expect(parseFileSizeToMB("100 Zettabytes")).toBe(100);
        expect(consoleSpy).toHaveBeenCalledWith(
            expect.stringContaining("Unrecognized"),
            "ZETTABYTES",
            expect.any(String),
            "100 Zettabytes"
        );
        consoleSpy.mockRestore();
    });

    // --- formatFileSize Tests ---

    test("should format MB as MB", () => {
        const { formatFileSize } = getGlobalFunctions();
        expect(formatFileSize(500.5)).toBe("500.50 MB");
    });

    test("should format values >= 1024 MB as GB", () => {
        const { formatFileSize } = getGlobalFunctions();
        expect(formatFileSize(2048)).toBe("2.00 GB"); // 2 GB
    });

    test("should return Unknown for invalid input", () => {
        const { formatFileSize } = getGlobalFunctions();
        expect(formatFileSize(null)).toBe("Unknown");
    });
});

describe("search.js Filter Logic (DOM dependent)", () => {
    let setupData; // holds the return value of setup for all test use

    beforeEach(() => {
        // The universally-defined setup function runs here, loading the DOM and mocks for each test.
        setupData = setup();
    });

    // --- initializeFilters Tests ---

    test("initializeFilters should configure native date input constraints", () => {
        const dateFrom = document.getElementById("date-from-filter");
        const dateTo = document.getElementById("date-to-filter");

        dateFrom.value = "2024-01-01";
        dateFrom.dispatchEvent(new Event("change"));
        expect(dateTo.min).toBe("2024-01-01");

        dateTo.value = "2024-02-01";
        dateTo.dispatchEvent(new Event("change"));
        expect(dateFrom.max).toBe("2024-02-01");
    });

    // --- applyFilters Tests ---

    test("applyFilters should filter by Category (Fiction) using substring match", () => {
        const { mockApply } = setupData;
        mockFilter("category-filter", "Fiction");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: "Fiction Science", "Fiction", "Fiction" rows. Excludes "Non-Fiction" due to regex.
        expect(visible).toHaveLength(3);
    });

    test("applyFilters should filter by Category (Science) using substring match", () => {
        const { mockApply } = setupData;
        mockFilter("category-filter", "Science");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: Only "Fiction Science" row.
        expect(visible).toHaveLength(1);
    });

    test("applyFilters should filter by File Size Range using native presets", () => {
        const { mockApply } = setupData;
        // Test preset 500 MB - 2 GB
        mockFilter("file-size-filter", "500mb_2gb");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: 500 MB row, 1.5 GB row.
        expect(visible).toHaveLength(2);
    });

    test("applyFilters should filter by native Date Range", () => {
        const { mockApply } = setupData;
        mockFilter("date-from-filter", "2024-01-01");
        mockFilter("date-to-filter", "2024-01-31");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // "01 Jan 2024" matches.
        expect(visible).toHaveLength(1);
    });

    test("clearFilters should reset all inputs and show all rows", () => {
        const { mockClear } = setupData;

        // Simulate filters applied previously
        document.querySelectorAll(".result-row")[0].style.display = "none";
        mockFilter("category-filter", "Fiction");
        mockFilter("file-size-filter", "500mb_2gb");
        mockFilter("date-from-filter", "2024-01-01");

        mockClear();

        // Check if values are reset
        expect(document.getElementById("category-filter").value).toBe("");
        expect(document.getElementById("file-size-filter").value).toBe("");
        expect(document.getElementById("date-from-filter").value).toBe("");
        expect(document.getElementById("date-to-filter").value).toBe("");

        // Check if all rows are visible
        document.querySelectorAll(".result-row").forEach((row) => {
            expect(row.style.display).toBe("");
        });
    });
});

describe("search.js UI Spinner Logic", () => {
    // FIX: Declare setupData variable to be accessible in tests
    let setupData;

    beforeEach(() => {
        // FIX: Assign return value of setup() to setupData
        setupData = setup();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    test("showLoadingSpinner should disable button and show spinner", () => {
        const { functions } = setupData;
        const button = document.querySelector(".search-button");
        const spinner = document.getElementById("button-spinner");

        expect(button.disabled).toBe(false);
        expect(spinner.style.display).toBe("none");

        functions.showLoadingSpinner();

        expect(button.disabled).toBe(true);
        // FIX: Use textContent for JSDOM compatibility
        expect(button.querySelector(".button-text").textContent).toBe("Searching...");
        expect(spinner.style.display).toBe("inline-block");
    });

    test("hideLoadingSpinner should re-enable button and hide spinner", () => {
        const { functions } = setupData;
        const button = document.querySelector(".search-button");
        const spinner = document.getElementById("button-spinner");

        // Set initial loading state
        functions.showLoadingSpinner();

        functions.hideLoadingSpinner();

        expect(button.disabled).toBe(false);
        // FIX: Use textContent for JSDOM compatibility
        expect(button.querySelector(".button-text").textContent).toBe("Search");
        expect(spinner.style.display).toBe("none");
    });

    test("Scrolling messages should appear after 3 seconds", () => {
        const { functions } = setupData;
        const messageScroller = document.getElementById("message-scroller");

        functions.showLoadingSpinner();
        expect(messageScroller.style.display).toBe("none");

        // Advance 3 seconds
        jest.advanceTimersByTime(3000);

        expect(messageScroller.style.display).toBe("block");
        expect(document.getElementById("scrolling-message").textContent).not.toBe("");
    });
});

describe("search.js Unit Tests - Progressive Search & Prefetch", () => {
    beforeEach(() => {
        setup();
    });

    test("createResultRowElement builds proper DOM table row", () => {
        const { createResultRowElement } = getGlobalFunctions();
        const book = {
            title: "Dune",
            link: "https://audiobookbay.lu/dune",
            cover: "https://audiobookbay.lu/cover.jpg",
            category: ["Sci-Fi, Fantasy"],
            language: "English",
            format: "M4B",
            bitrate: "128 Kbps",
            file_size: "500 MB",
            post_date: "01 Jan 2024",
        };

        const row = createResultRowElement(book);
        expect(row.tagName).toBe("TR");
        expect(row.className).toContain("result-row");
        expect(row.dataset.category).toBe("Sci-Fi, Fantasy");
        expect(row.dataset.language).toBe("English");
        expect(row.querySelector(".book-title").textContent).toBe("Dune");
        expect(row.querySelector(".category-link").textContent).toBe("Sci-Fi");
        expect(row.querySelector(".send-torrent-btn").dataset.title).toBe("Dune");
    });

    test("streamRemainingPages fetches subsequent pages and appends rows", async () => {
        const { streamRemainingPages } = getGlobalFunctions();
        const tbody = document.getElementById("results-table-body");
        const initialRowCount = tbody.querySelectorAll(".result-row").length;

        // Mock fetch
        global.fetch = jest.fn().mockImplementation((url) => {
            if (url.includes("page=2")) {
                return Promise.resolve({
                    ok: true,
                    json: () =>
                        Promise.resolve({
                            books: [
                                {
                                    title: "Streamed Book 1",
                                    link: "/book-1",
                                    category: ["Adventure"],
                                    language: "English",
                                    format: "MP3",
                                    bitrate: "64 Kbps",
                                    file_size: "100 MB",
                                    post_date: "02 Feb 2024",
                                },
                            ],
                            has_more: false,
                            page: 2,
                        }),
                });
            }
            return Promise.resolve({
                ok: true,
                json: () => Promise.resolve({ books: [], has_more: false, page: 3 }),
            });
        });

        await streamRemainingPages("dune", 2, 3);

        const newRowCount = tbody.querySelectorAll(".result-row").length;
        expect(newRowCount).toBe(initialRowCount + 1);
        expect(tbody.textContent).toContain("Streamed Book 1");
        expect(global.fetch).toHaveBeenCalledWith("/api/search?query=dune&page=2");
    });

    test("loadNextPage fetches page, appends rows, and manages indicator state", async () => {
        const { loadNextPage } = getGlobalFunctions();
        const tbody = document.getElementById("results-table-body");
        const initialRowCount = tbody.querySelectorAll(".result-row").length;

        // Add load-more-indicator and load-more-btn to DOM
        const indicator = document.createElement("div");
        indicator.id = "load-more-indicator";
        indicator.innerHTML = '<span id="load-more-loading"></span><button id="load-more-btn"></button>';
        document.body.appendChild(indicator);

        global.fetch = jest.fn().mockReturnValue(
            Promise.resolve({
                ok: true,
                json: () =>
                    Promise.resolve({
                        books: [
                            {
                                title: "Infinite Expanse 1",
                                link: "/expanse-1",
                                category: ["Sci-Fi"],
                                language: "English",
                                format: "M4B",
                                bitrate: "128 Kbps",
                                file_size: "600 MB",
                                post_date: "05 Mar 2024",
                            },
                        ],
                        has_more: true,
                        page: 2,
                    }),
            })
        );

        const hasMore = await loadNextPage("expanse");
        expect(hasMore).toBe(true);

        const newRowCount = tbody.querySelectorAll(".result-row").length;
        expect(newRowCount).toBe(initialRowCount + 1);
        expect(tbody.textContent).toContain("Infinite Expanse 1");
        expect(global.fetch).toHaveBeenCalledWith("/api/search?query=expanse&page=2");
    });

    test("initInfiniteScroll configures IntersectionObserver or falls back gracefully", () => {
        const { initInfiniteScroll } = getGlobalFunctions();
        const indicator = document.createElement("div");
        indicator.id = "load-more-indicator";
        document.body.appendChild(indicator);

        const mockObserve = jest.fn();
        const mockDisconnect = jest.fn();
        global.IntersectionObserver = jest.fn().mockImplementation((callback) => ({
            observe: mockObserve,
            disconnect: mockDisconnect,
        }));

        initInfiniteScroll("the expanse");
        expect(global.IntersectionObserver).toHaveBeenCalled();
        expect(mockObserve).toHaveBeenCalledWith(indicator);
    });

    test("initHoverPrefetch fires fetch on category pill hover after 150ms", () => {
        jest.useFakeTimers();
        const { initHoverPrefetch } = getGlobalFunctions();
        const tbody = document.getElementById("results-table-body");

        // Add a mock category link
        const a = document.createElement("a");
        a.className = "category-tag category-link";
        a.href = "/?query=Brandon+Sanderson";
        tbody.appendChild(a);

        global.fetch = jest.fn().mockReturnValue(Promise.resolve({ ok: true }));

        initHoverPrefetch();

        // Simulate mouseenter
        a.dispatchEvent(new Event("mouseenter"));

        // Before timer: no fetch
        expect(global.fetch).not.toHaveBeenCalled();

        // Advance 160ms
        jest.advanceTimersByTime(160);

        expect(global.fetch).toHaveBeenCalledTimes(1);
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining("/api/search?query=Brandon%20Sanderson&page=1"),
            expect.any(Object)
        );

        jest.useRealTimers();
    });

    test("setViewMode toggles grid and list mode and persists to localStorage", () => {
        const { setViewMode } = getGlobalFunctions();

        const container = document.createElement("div");
        container.id = "results-container";
        const listBtn = document.createElement("button");
        listBtn.id = "view-list-btn";
        const gridBtn = document.createElement("button");
        gridBtn.id = "view-grid-btn";

        document.body.appendChild(container);
        document.body.appendChild(listBtn);
        document.body.appendChild(gridBtn);

        // Test setting to grid
        setViewMode("grid");
        expect(container.classList.contains("view-grid")).toBe(true);
        expect(container.classList.contains("view-list")).toBe(false);
        expect(gridBtn.classList.contains("active")).toBe(true);
        expect(listBtn.classList.contains("active")).toBe(false);
        expect(localStorage.getItem("viewMode")).toBe("grid");

        // Test setting to list
        setViewMode("list");
        expect(container.classList.contains("view-list")).toBe(true);
        expect(container.classList.contains("view-grid")).toBe(false);
        expect(listBtn.classList.contains("active")).toBe(true);
        expect(gridBtn.classList.contains("active")).toBe(false);
        expect(localStorage.getItem("viewMode")).toBe("list");
    });

    test("initFloatingHud toggles visibility on scroll and manages drawer", () => {
        const { initFloatingHud, syncHudFilters } = getGlobalFunctions();

        // Build mock HUD elements
        const hud = document.createElement("aside");
        hud.id = "floating-filter-hud";
        const toggleBtn = document.createElement("button");
        toggleBtn.id = "hud-filter-toggle";
        const drawer = document.createElement("div");
        drawer.id = "hud-filter-drawer";
        const closeBtn = document.createElement("button");
        closeBtn.id = "hud-drawer-close";
        const applyBtn = document.createElement("button");
        applyBtn.id = "hud-apply-filters-btn";
        const clearBtn = document.createElement("button");
        clearBtn.id = "hud-clear-filters-btn";
        const topBtn = document.createElement("button");
        topBtn.id = "hud-top-btn";
        const badge = document.createElement("span");
        badge.id = "hud-filter-badge";

        // Main selects are already set up in setup(): category-filter, language-filter, bitrate-filter, format-filter

        // HUD selects
        ["category", "language", "bitrate", "format"].forEach((field) => {
            const hudSelect = document.createElement("select");
            hudSelect.id = `hud-${field}-filter`;
            const optNone = document.createElement("option");
            optNone.value = "";
            const optVal = document.createElement("option");
            optVal.value = "TestVal";
            hudSelect.appendChild(optNone);
            hudSelect.appendChild(optVal);
            document.body.appendChild(hudSelect);
        });

        // Add matching option to main category select
        const catSelect = document.getElementById("category-filter");
        if (catSelect) {
            const opt = document.createElement("option");
            opt.value = "TestVal";
            catSelect.appendChild(opt);
        }

        document.body.appendChild(hud);
        document.body.appendChild(toggleBtn);
        document.body.appendChild(drawer);
        document.body.appendChild(closeBtn);
        document.body.appendChild(applyBtn);
        document.body.appendChild(clearBtn);
        document.body.appendChild(topBtn);
        document.body.appendChild(badge);

        window.scrollTo = jest.fn();
        window.requestAnimationFrame = (cb) => cb();

        initFloatingHud();

        // Simulate scroll past 350
        Object.defineProperty(window, "scrollY", { value: 400, writable: true });
        window.dispatchEvent(new Event("scroll"));
        expect(hud.classList.contains("visible")).toBe(true);

        // Toggle drawer
        toggleBtn.click();
        expect(drawer.classList.contains("open")).toBe(true);

        // Close drawer via closeBtn
        closeBtn.click();
        expect(drawer.classList.contains("open")).toBe(false);

        // Test top button
        topBtn.click();
        expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });

        // Test syncHudFilters
        const hudCatSelect = document.getElementById("hud-category-filter");
        hudCatSelect.value = "TestVal";
        syncHudFilters(true);
        expect(catSelect.value).toBe("TestVal");
        expect(badge.textContent).toBe("1");
        expect(badge.style.display).toBe("inline-block");

        // Clear
        catSelect.value = "";
        hudCatSelect.value = "";
        syncHudFilters(false);
        expect(badge.style.display).toBe("none");
    });

    test("initTopFilterDrawer manages overlay opening, closing, and resets", () => {
        const { initTopFilterDrawer, clearFilters } = getGlobalFunctions();

        const toggleBtn = document.createElement("button");
        toggleBtn.id = "toolbar-filter-toggle";
        const overlay = document.createElement("div");
        overlay.id = "filter-drawer-overlay";
        const closeBtn = document.createElement("button");
        closeBtn.id = "filter-drawer-close";
        let applyBtn = document.getElementById("filter-button");
        if (!applyBtn) {
            applyBtn = document.createElement("button");
            applyBtn.id = "filter-button";
            document.body.appendChild(applyBtn);
        }
        const toolbarClearBtn = document.createElement("button");
        toolbarClearBtn.id = "toolbar-clear-btn";

        document.body.appendChild(toggleBtn);
        document.body.appendChild(overlay);
        document.body.appendChild(closeBtn);
        document.body.appendChild(toolbarClearBtn);

        initTopFilterDrawer();

        // Open
        toggleBtn.click();
        expect(overlay.classList.contains("open")).toBe(true);
        expect(overlay.getAttribute("aria-hidden")).toBe("false");

        // Close via close button
        closeBtn.click();
        expect(overlay.classList.contains("open")).toBe(false);
        expect(overlay.getAttribute("aria-hidden")).toBe("true");

        // Open and close via Escape
        toggleBtn.click();
        expect(overlay.classList.contains("open")).toBe(true);
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
        expect(overlay.classList.contains("open")).toBe(false);

        // Open and close via Apply
        toggleBtn.click();
        expect(overlay.classList.contains("open")).toBe(true);
        applyBtn.click();
        expect(overlay.classList.contains("open")).toBe(false);

        // Toolbar clear button
        const catSelect = document.getElementById("category-filter");
        if (catSelect) catSelect.value = "Fiction";
        toolbarClearBtn.click();
        if (catSelect) expect(catSelect.value).toBe("");
    });
});
