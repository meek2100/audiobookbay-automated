/**
 * @jest-environment jsdom
 */

// NOTE: statusJsContent is available globally from jest.setup.js

// Mock fetch before loading the script
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Spy on console.error
const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});

// Add deleteTorrent to window so status.js can call it (it's defined in actions.js, but we mock it here)
window.deleteTorrent = jest.fn();

// --- SETUP ---
// Evaluate the script ONCE for the entire suite.
// This attaches the DOMContentLoaded listener one time.
beforeAll(() => {
    eval(global.statusJsContent);
});

// Helper functions (exposed by status.js via window)
// We access them dynamically in tests to ensure we get the evaluated versions
const getUpdateTable = () => window.updateTable;

describe("status.js - UI Logic", () => {
    let tbody;

    beforeEach(() => {
        document.body.innerHTML = '<table><tbody id="status-table-body"></tbody></table>';
        tbody = document.getElementById("status-table-body");
        mockFetch.mockClear();
        window.deleteTorrent.mockClear();
    });

    test("updateTable should show empty message for empty list", () => {
        window.updateTable(tbody, []);
        expect(tbody.innerHTML).toContain("No active downloads found");
        expect(tbody.querySelectorAll("tr").length).toBe(1); // 1 row for the message
    });

    test("updateTable should show empty message for null/undefined", () => {
        window.updateTable(tbody, null);
        expect(tbody.innerHTML).toContain("No active downloads found");
    });

    test("updateTable should render rows for torrents", () => {
        const torrents = [
            { id: "123", name: "Book A", progress: 50.5, state: "Downloading", size: "1 GB" },
            { id: "456", name: "Book B", progress: 100, state: "Seeding", size: "500 MB" },
        ];

        window.updateTable(tbody, torrents);

        const rows = tbody.querySelectorAll("tr");
        expect(rows.length).toBe(2);

        // Check content of first row
        expect(rows[0].innerHTML).toContain("Book A");
        expect(rows[0].innerHTML).toContain("50.5%");
        expect(rows[0].innerHTML).toContain("Downloading");
        expect(rows[0].innerHTML).toContain("1 GB");

        // Check action button
        const btn = rows[0].querySelector("button");
        expect(btn).not.toBeNull();
        expect(btn.getAttribute("onclick")).toContain("deleteTorrent('123')");
    });

    test("updateTable should escape XSS in names", () => {
        const malicious = [
            { id: "666", name: "<script>alert('xss')</script>", progress: 0, state: "Bad", size: "0 B" },
        ];

        window.updateTable(tbody, malicious);

        // The innerHTML should NOT contain the script tag literally interpreted
        expect(tbody.innerHTML).toContain("&lt;script&gt;alert('xss')&lt;/script&gt;");
        expect(tbody.innerHTML).not.toContain("<script>alert");
    });
});

describe("status.js - Polling Mechanism", () => {
    beforeEach(() => {
        document.body.innerHTML = '<table><tbody id="status-table-body"></tbody></table>';
        jest.useFakeTimers();
        mockFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve([]),
        });
        consoleErrorSpy.mockClear();
        mockFetch.mockClear();
    });

    afterEach(() => {
        // CRITICAL: Stop the poll loop to prevent it from bleeding into the next test
        if (window.statusInterval) {
            clearInterval(window.statusInterval);
            window.statusInterval = null;
        }
        jest.useRealTimers();
    });

    test("Polling should trigger fetch every 5 seconds", async () => {
        // Trigger DOMContentLoaded to start the interval
        document.dispatchEvent(new Event("DOMContentLoaded"));

        // Fast-forward 5 seconds
        jest.advanceTimersByTime(5000);

        expect(mockFetch).toHaveBeenCalledWith("/status?json=1");
        expect(mockFetch).toHaveBeenCalledTimes(1);

        // Another 5 seconds
        jest.advanceTimersByTime(5000);
        expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    test("Polling should handle fetch errors gracefully", async () => {
        mockFetch.mockRejectedValue(new Error("Network Error"));

        document.dispatchEvent(new Event("DOMContentLoaded"));
        jest.advanceTimersByTime(5000);

        // Should have called fetch
        expect(mockFetch).toHaveBeenCalled();

        // Wait for promise rejection handling
        await Promise.resolve();

        // Should have logged error (spy)
        expect(consoleErrorSpy).toHaveBeenCalled();
    });

    test("Polling should handle non-200 responses", async () => {
        mockFetch.mockResolvedValue({ ok: false, status: 500 });

        document.dispatchEvent(new Event("DOMContentLoaded"));
        jest.advanceTimersByTime(5000);

        expect(mockFetch).toHaveBeenCalled();

        await Promise.resolve();

        expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining("Status poll failed"), 500);
    });

    test("Polling should NOT start if table body is missing", () => {
        document.body.innerHTML = "<div>No Table Here</div>";
        // Trigger event
        document.dispatchEvent(new Event("DOMContentLoaded"));

        jest.advanceTimersByTime(5000);
        expect(mockFetch).not.toHaveBeenCalled();
    });
});
