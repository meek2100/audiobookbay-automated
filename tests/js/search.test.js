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

    // Setup Filter Controls (required for initialization)
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
            <select id="category-filter"><option value="">All Categories</option></select>
            <select id="language-filter"><option value="">All Languages</option></select>
            <select id="bitrate-filter"><option value="">All Bitrates</option></select>
            <select id="format-filter"><option value="">All Formats</option></select>
            <input type="text" id="date-range-filter" />
            <div class="filter-row"><div class="filter-controls"><div class="file-size-filter-wrapper"><div id="file-size-slider"></div></div></div><div class="filter-buttons"><button id="filter-button"></button><button id="clear-button"></button></div></div>
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

    // Reset and re-run initialization mocks
    global.flatpickr.mockClear();
    global.noUiSlider.create.mockClear();

    const functions = getGlobalFunctions();
    functions.initializeFilters();

    // Manually trigger DOMContentLoaded to run initializeFilters setup
    document.dispatchEvent(new Event("DOMContentLoaded"));

    // Extract the mock instances (which are now globally mocked)
    const mockFlatpickr = global.flatpickr.mock.results[global.flatpickr.mock.results.length - 1].value;
    const mockNoUiSlider =
        global.noUiSlider.create.mock.results[global.noUiSlider.create.mock.results.length - 1].value;

    return {
        functions,
        mockFlatpickr,
        mockNoUiSlider,
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

    test("initializeFilters should populate all select menus correctly", () => {
        const categoryFilter = document.getElementById("category-filter");
        const options = Array.from(categoryFilter.querySelectorAll("option"))
            .map((opt) => opt.value)
            .filter((v) => v !== "");

        // Expect individual category terms, sorted alphabetically
        expect(options).toEqual(["Fiction", "Non-Fiction", "Science"]);

        const formatFilter = document.getElementById("format-filter");
        const formatOptions = Array.from(formatFilter.querySelectorAll("option"))
            .map((opt) => opt.value)
            .filter((v) => v !== "");
        expect(formatOptions).toEqual(["M4B", "MP3"]);
    });

    test("initializeFilters should initialize date and size pickers correctly", () => {
        const { mockNoUiSlider } = setupData;

        expect(global.flatpickr).toHaveBeenCalled();
        expect(global.noUiSlider.create).toHaveBeenCalled();

        const noUiSliderOptions = mockNoUiSlider.options;
        expect(noUiSliderOptions.range.min).toBeCloseTo(100);
        expect(noUiSliderOptions.range.max).toBeCloseTo(10240); // 10 GB
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

    test("applyFilters should filter by File Size Range", () => {
        const { mockNoUiSlider, mockApply } = setupData;
        // Mock slider range: Min 150MB, Max 2GB (2048MB)
        mockNoUiSlider.get.mockReturnValue(["150", "2048"]);
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: 500 MB row, 1.5 GB row (1536 MB).
        expect(visible).toHaveLength(2);
    });

    test("clearFilters should reset all inputs and show all rows", () => {
        const { mockFlatpickr, mockNoUiSlider, mockClear } = setupData;

        // Simulate a filter applied previously
        document.querySelectorAll(".result-row")[0].style.display = "none";
        mockFilter("category-filter", "Fiction");

        mockClear();

        // Check if select values are reset
        expect(document.getElementById("category-filter").value).toBe("");
        // Check if date picker is cleared
        expect(mockFlatpickr.clear).toHaveBeenCalled();
        // Check if slider is reset
        expect(mockNoUiSlider.reset).toHaveBeenCalled();
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
