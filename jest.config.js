/**
 * @jest-environment jsdom
 */

const fs = require("fs");
const path = require("path");

// We need to fetch and evaluate the source script to make its global functions available to JSDOM.
const searchJsPath = path.resolve(__dirname, "app/static/js/search.js");
const searchJsContent = fs.readFileSync(searchJsPath, "utf8");

// --- Global Mocks ---

// Mock flatpickr instance creator. Attach options and common methods for testing.
global.flatpickr = jest.fn((element, options) => ({
    selectedDates: [],
    clear: jest.fn(),
    options, // attach options to mock instance for testing
}));

// Mock noUiSlider instance creator. Attach options and common methods for testing.
global.noUiSlider = {
    create: jest.fn((element, options) => ({
        get: jest.fn(() => options.start), // Return the start values (the whole range by default)
        reset: jest.fn(),
        options, // attach options to mock instance for testing
    })),
};

// --- Initialization & Setup ---

// Function to retrieve the globally exposed functions from the evaluated script
const getGlobalFunctions = () => {
    // The functions are explicitly attached to window in the source file (search.js).
    return {
        parseFileSizeToMB: window.parseFileSizeToMB,
        formatFileSize: window.formatFileSize,
        initializeFilters: window.initializeFilters,
        applyFilters: window.applyFilters,
        clearFilters: window.clearFilters,
    };
};

// Evaluate the script content once. This attaches all exposed functions to the global window object.
eval(searchJsContent);

// Helper to create a mock result row
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

// Helper to set up the DOM, initialize filters, and return the mock instances
const setupDOMAndMocks = () => {
    // 1. Clear DOM
    document.body.innerHTML = "";

    // 2. Setup Filter Controls (required for initialization)
    document.body.innerHTML = `
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

    // 3. Add mock result rows to the DOM
    const tbody = document.getElementById("results-table-body");
    tbody.appendChild(createResultRow("Fiction", "English", "128 Kbps", "500 MB", "01 Jan 2024", "M4B"));
    tbody.appendChild(createResultRow("Non-Fiction", "Spanish", "64 Kbps", "1.5 GB", "15 Feb 2024", "MP3"));
    tbody.appendChild(createResultRow("Fiction", "English", "128 Kbps", "100 MB", "20 Dec 2023", "M4B"));
    tbody.appendChild(createResultRow("Fiction", "English", "N/A", "10 GB", "N/A", "MP3")); // Max size row: 10240 MB
    tbody.appendChild(createResultRow("N/A", "N/A", "N/A", "N/A", "N/A", "N/A")); // Fully N/A row

    // 4. Clear mock history before running initialization
    global.flatpickr.mockClear();
    global.noUiSlider.create.mockClear();

    // 5. Run initialization
    const functions = getGlobalFunctions();
    // This call assigns instances to window.datePicker and window.fileSizeSlider
    functions.initializeFilters();

    // 6. Retrieve the mock instances using the global variables assigned by the script
    const mockFlatpickrInstance = window.datePicker;
    const mockNoUiSliderInstance = window.fileSizeSlider;

    // Return everything needed for testing
    return {
        functions,
        mockFlatpickr: mockFlatpickrInstance,
        mockNoUiSlider: mockNoUiSliderInstance,
        mockFilter: (id, value) => {
            document.getElementById(id).value = value;
        },
        mockApply: functions.applyFilters,
        mockClear: functions.clearFilters,
    };
};

// --- START TESTS ---

describe("search.js Unit Tests - File Size Utilities", () => {
    // These functions are globally exposed and don't require DOM setup
    const { parseFileSizeToMB, formatFileSize } = getGlobalFunctions();

    test("should return correct MB for GB", () => {
        expect(parseFileSizeToMB("1.5 GB")).toBe(1536); // 1.5 * 1024
    });

    test("should return correct MB for TB", () => {
        expect(parseFileSizeToMB("1 TB")).toBe(1048576); // 1 * 1024 * 1024
    });

    test("should return correct MB for MB", () => {
        expect(parseFileSizeToMB("512 MB")).toBe(512);
    });

    test("should handle fractional MB", () => {
        expect(parseFileSizeToMB("3.14 MB")).toBe(3.14);
    });

    test("should handle KB (less than 1 MB)", () => {
        expect(parseFileSizeToMB("500 KB")).toBeCloseTo(0.48828125); // 500 / 1024
    });

    test("should handle PB (edge case)", () => {
        expect(parseFileSizeToMB("0.001 PB")).toBeCloseTo(1073741.824); // 0.001 * 1024^3
    });

    test("should return null for N/A or empty string", () => {
        expect(parseFileSizeToMB("N/A")).toBeNull();
        expect(parseFileSizeToMB(" ")).toBeNull();
    });

    test("should return value for unrecognized format", () => {
        // The implementation falls back to returning the size value if no recognized unit is found
        expect(parseFileSizeToMB("100 units")).toBe(100);
        expect(parseFileSizeToMB("invalid")).toBeNull();
    });

    // --- formatFileSize Tests ---

    test("should format MB as MB", () => {
        expect(formatFileSize(500.5)).toBe("500.50 MB");
    });

    test("should format values >= 1024 MB as GB", () => {
        expect(formatFileSize(2048)).toBe("2.00 GB"); // 2 GB
        expect(formatFileSize(1500)).toBe("1.46 GB");
    });

    test("should format values >= 1048576 MB as TB", () => {
        expect(formatFileSize(1048576 * 3)).toBe("3.00 TB"); // 3 TB
    });

    test("should return N/A for invalid input", () => {
        expect(formatFileSize(null)).toBe("N/A");
        expect(formatFileSize(NaN)).toBe("N/A");
    });
});

describe("search.js Filter Logic (DOM dependent)", () => {
    let setup; // holds the return value of setupDOMAndMocks for all test use

    beforeEach(() => {
        setup = setupDOMAndMocks();
    });

    // --- initializeFilters Tests ---

    test("initializeFilters should populate all select menus correctly", () => {
        const categoryFilter = document.getElementById("category-filter");
        const options = Array.from(categoryFilter.querySelectorAll("option"))
            .map((opt) => opt.value)
            .filter((v) => v !== "");

        expect(options).toEqual(["Fiction", "Non-Fiction"]);
    });

    test("initializeFilters should initialize date and size pickers correctly", () => {
        // Access mock instances from the setup object
        const { mockNoUiSlider } = setup;

        expect(global.flatpickr).toHaveBeenCalled();
        expect(global.noUiSlider.create).toHaveBeenCalled();

        // Assert the mock instance exists and has the correct options attached
        expect(mockNoUiSlider).toBeDefined();

        const noUiSliderOptions = mockNoUiSlider.options;
        expect(noUiSliderOptions.range.min).toBeCloseTo(100);
        expect(noUiSliderOptions.range.max).toBeCloseTo(10240); // 10 GB
    });

    // --- applyFilters Tests ---

    test("applyFilters should filter by Category (Fiction)", () => {
        const { mockFilter, mockApply } = setup;
        mockFilter("category-filter", "Fiction");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        expect(visible).toHaveLength(3);
    });

    test("applyFilters should filter by Language (Spanish)", () => {
        const { mockFilter, mockApply } = setup;
        mockFilter("language-filter", "Spanish");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        expect(visible).toHaveLength(1);
    });

    test("applyFilters should filter by Format (M4B)", () => {
        const { mockFilter, mockApply } = setup;
        mockFilter("format-filter", "M4B");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        expect(visible).toHaveLength(2);
    });

    test("applyFilters should filter by File Size Range", () => {
        const { mockNoUiSlider, mockApply } = setup;
        // Mock slider range set to exclude both the smallest (100MB) and largest (10GB)
        // Range: Min 150MB, Max 2GB (2048MB)
        mockNoUiSlider.get.mockReturnValue(["150", "2048"]);
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: 500 MB row, 1.5 GB row (1536 MB).
        expect(visible).toHaveLength(2);
    });

    test("applyFilters should filter by Date Range", () => {
        const { mockFlatpickr, mockApply } = setup;
        // Mock flatpickr to select a range around Jan 2024
        const date1 = new Date("2024-01-01");
        const date2 = new Date("2024-02-15");
        // Manually set the mock flatpickr instance's selectedDates
        mockFlatpickr.selectedDates = [date1, date2];
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: 01 Jan 2024, 15 Feb 2024.
        expect(visible).toHaveLength(2);
    });

    test("applyFilters should apply multiple filters simultaneously", () => {
        const { mockFilter, mockNoUiSlider, mockApply } = setup;
        // Filter 1: Category: Fiction
        mockFilter("category-filter", "Fiction");
        // Filter 2: Size: Only 100MB row is Fiction and smaller than max. Range: [90, 200]
        mockNoUiSlider.get.mockReturnValue(["90", "200"]);
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        expect(visible).toHaveLength(1);
    });

    test("clearFilters should reset all inputs and show all rows", () => {
        const { mockFlatpickr, mockNoUiSlider, mockFilter, mockClear } = setup;
        // Simulate a filter applied previously
        const allRows = document.querySelectorAll(".result-row");
        allRows[0].style.display = "none";
        allRows[1].style.display = "none";

        mockFilter("category-filter", "Fiction");
        mockClear();

        // Check if select values are reset
        expect(document.getElementById("category-filter").value).toBe("");
        // Check if date picker is cleared
        expect(mockFlatpickr.clear).toHaveBeenCalled();
        // Check if slider is reset
        expect(mockNoUiSlider.reset).toHaveBeenCalled();
        // Check if all rows are visible
        allRows.forEach((row) => {
            expect(row.style.display).toBe("");
        });
    });
});
