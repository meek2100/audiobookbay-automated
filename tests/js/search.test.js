/**
 * @jest-environment jsdom
 */

// Evaluate the script content once. This attaches all exposed functions (parseFileSizeToMB, etc.) to the global window object.
// The functions are now explicitly attached to the window object in the source file.
eval(searchJsContent);

// Manually trigger DOMContentLoaded to run initializeFilters setup
document.dispatchEvent(new Event("DOMContentLoaded"));

// Function to extract the global functions that were exposed by search.js
const getGlobalFunctions = () => {
    // The functions are now explicitly attached to window in the source file.
    return {
        parseFileSizeToMB: window.parseFileSizeToMB,
        formatFileSize: window.formatFileSize,
        initializeFilters: window.initializeFilters,
        applyFilters: window.applyFilters,
        clearFilters: window.clearFilters,
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

// --- START TESTS ---

describe("search.js Unit Tests - File Size Utilities", () => {
    const { parseFileSizeToMB, formatFileSize } = getGlobalFunctions();

    // --- parseFileSizeToMB Tests (The core logic for filters) ---

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
        // As per the implemented logic in search.js, it falls through to the final return if no other unit matches.
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
    let functions;
    let mockFlatpickr, mockNoUiSlider;

    // Helper to setup mock data and extract functions
    const setup = () => {
        // Clear DOM before each test
        document.body.innerHTML = "";

        // Setup Filter Controls (required for initializeFilters and applyFilters)
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

        // Add mock result rows to the DOM
        const tbody = document.getElementById("results-table-body");
        tbody.appendChild(createResultRow("Fiction", "English", "128 Kbps", "500 MB", "01 Jan 2024", "M4B"));
        tbody.appendChild(createResultRow("Non-Fiction", "Spanish", "64 Kbps", "1.5 GB", "15 Feb 2024", "MP3"));
        tbody.appendChild(createResultRow("Fiction", "English", "128 Kbps", "100 MB", "20 Dec 2023", "M4B"));
        tbody.appendChild(createResultRow("Fiction", "English", "N/A", "10 GB", "N/A", "MP3")); // Max size row: 10240 MB
        tbody.appendChild(createResultRow("N/A", "N/A", "N/A", "N/A", "N/A", "N/A")); // Fully N/A row

        // Reset and re-run initialization to populate the filters and set up state
        global.flatpickr.mockClear();
        global.noUiSlider.create.mockClear();

        functions = getGlobalFunctions();
        functions.initializeFilters();

        // Extract the mock instances (which are now globally mocked)
        // We look up the latest mock instances since they are recreated on each test setup
        mockFlatpickr = global.flatpickr.mock.results[global.flatpickr.mock.results.length - 1].value;
        mockNoUiSlider = global.noUiSlider.create.mock.results[global.noUiSlider.create.mock.results.length - 1].value;
    };

    // Helper to filter and apply
    const mockFilter = (id, value) => {
        document.getElementById(id).value = value;
    };
    const mockApply = () => functions.applyFilters();
    const mockClear = () => functions.clearFilters();

    // --- TESTS ---

    test("initializeFilters should populate all select menus correctly", () => {
        setup();
        const categoryFilter = document.getElementById("category-filter");
        const options = Array.from(categoryFilter.querySelectorAll("option"))
            .map((opt) => opt.value)
            .filter((v) => v !== ""); // Filter out default empty option

        // Expected sorted unique values, excluding initial "" and filtered "N/A"
        expect(options).toEqual(["Fiction", "Non-Fiction"]);

        const formatFilter = document.getElementById("format-filter");
        const formatOptions = Array.from(formatFilter.querySelectorAll("option"))
            .map((opt) => opt.value)
            .filter((v) => v !== "");
        expect(formatOptions).toEqual(["M4B", "MP3"]);
    });

    test("initializeFilters should initialize date and size pickers correctly", () => {
        setup();

        expect(global.flatpickr).toHaveBeenCalled();
        expect(global.noUiSlider.create).toHaveBeenCalled();

        // Verify noUiSlider range creation uses calculated min/max MB (100 MB to 10 GB/10240 MB)
        // Corrected assertion: 10 GB * 1024 MB/GB = 10240 MB
        const noUiSliderOptions = mockNoUiSlider.options;
        expect(noUiSliderOptions.range.min).toBeCloseTo(100);
        expect(noUiSliderOptions.range.max).toBeCloseTo(10240);
    });

    test("applyFilters should filter by Category (Fiction)", () => {
        setup();
        mockFilter("category-filter", "Fiction");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: 500MB (Fiction), 100MB (Fiction), 10GB (Fiction). Excludes: Non-Fiction, N/A.
        expect(visible).toHaveLength(3);
        expect(visible.map((r) => r.dataset.category)).toEqual(["Fiction", "Fiction", "Fiction"]);
    });

    test("applyFilters should filter by Language (Spanish)", () => {
        setup();
        mockFilter("language-filter", "Spanish");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        expect(visible).toHaveLength(1);
        expect(visible[0].dataset.language).toBe("Spanish");
    });

    test("applyFilters should filter by Format (M4B)", () => {
        setup();
        mockFilter("format-filter", "M4B");
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        expect(visible).toHaveLength(2);
        expect(visible.map((r) => r.dataset.format)).toEqual(["M4B", "M4B"]);
    });

    test("applyFilters should filter by File Size Range", () => {
        setup();
        // Mock slider range set to exclude both the smallest (100MB) and largest (10GB)
        // Range: Min 150MB, Max 2GB (2048MB)
        mockNoUiSlider.get.mockReturnValue(["150", "2048"]);
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Excludes: 100 MB row (too small), 10 GB row (too large), N/A size row.
        // Includes: 500 MB row, 1.5 GB row (1536 MB).
        expect(visible).toHaveLength(2);
        expect(visible.map((r) => r.dataset.fileSize)).toEqual(["500 MB", "1.5 GB"]);
    });

    test("applyFilters should filter by Date Range", () => {
        setup();
        // Mock flatpickr to select a range around Jan 2024
        const date1 = new Date("2024-01-01");
        const date2 = new Date("2024-02-15");
        mockFlatpickr.selectedDates = [date1, date2];
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        // Includes: 01 Jan 2024, 15 Feb 2024.
        // Excludes: 20 Dec 2023, N/A date rows.
        expect(visible).toHaveLength(2);
    });

    test("applyFilters should apply multiple filters simultaneously", () => {
        setup();
        // Filter 1: Category: Fiction
        mockFilter("category-filter", "Fiction");
        // Filter 2: Size: Only 100MB row is Fiction and smaller than max. Range: [90, 200]
        mockNoUiSlider.get.mockReturnValue(["90", "200"]);
        mockApply();

        const visible = Array.from(document.querySelectorAll(".result-row")).filter((r) => r.style.display === "");
        expect(visible).toHaveLength(1);
        expect(visible[0].dataset.fileSize).toBe("100 MB");
    });

    test("clearFilters should reset all inputs and show all rows", () => {
        setup();
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
