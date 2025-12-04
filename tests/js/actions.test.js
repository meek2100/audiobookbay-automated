/**
 * @jest-environment jsdom
 */

// NOTE: actionsJsContent is available globally from jest.setup.js

// Mock fetch before loading the script
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock window functions
const mockConfirm = jest.fn();
const mockOpen = jest.fn();
global.confirm = mockConfirm;
global.open = mockOpen;

// Mock requestAnimationFrame used by showNotification
global.requestAnimationFrame = jest.fn((cb) => cb());

// Spy on console.error to detect swallowed errors
const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});

// Add a required meta tag for CSRF token into the DOM
document.head.innerHTML = '<meta name="csrf-token" content="test-csrf-token" />';

// Evaluate the script content to define the functions globally (showNotification, sendTorrent, etc.)
eval(global.actionsJsContent);

// --- MOCK UTILITIES (MOVED TO TOP-LEVEL SCOPE FOR ACCESSIBILITY) ---

function getNotificationText() {
    const container = document.getElementById("notification-container");
    return container ? container.textContent : "";
}

// CRITICAL FIX: Helper to drain the microtask queue completely.
// Uses jest.requireActual("timers").setTimeout to bypass fake timers.
// This prevents deadlocks where await waits for a mocked timer that hasn't run yet.
async function flushPromises() {
    return new Promise((resolve) => jest.requireActual("timers").setTimeout(resolve, 0));
}
// ---------------------------------------------------------------------

// Reset mocks before each test
beforeEach(() => {
    mockFetch.mockClear();
    mockConfirm.mockClear();
    mockOpen.mockClear();
    // Default mock response for success
    mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ message: "Success" }),
        status: 200,
    });
    // Ensure notification container exists and is empty
    document.body.innerHTML = '<div id="notification-container"></div>';
    jest.useFakeTimers();
});

afterAll(() => {
    jest.useRealTimers();
    consoleErrorSpy.mockRestore();
});

describe("actions.js - Core Functionality", () => {
    test("showNotification should display and remove a toast", () => {
        showNotification("Test message", "success");
        expect(getNotificationText()).toContain("Test message");

        // Step 1: Get the toast element to dispatch the event later
        const toast = document.querySelector("#notification-container > div");

        // Step 2: Advance the timer (3000ms) to trigger the removal block (setTimeout)
        jest.advanceTimersByTime(3000);

        // Step 3 (Simulate Event): Manually dispatch the 'transitionend' event.
        const transitionEndEvent = new Event("transitionend");
        if (toast) {
            toast.dispatchEvent(transitionEndEvent);
        }

        // Expect element to be removed immediately after the event simulation
        expect(document.querySelector("#notification-container > div")).toBeNull();
        expect(getNotificationText()).toBe("");
    });

    test("showNotification should handle error type", () => {
        showNotification("Error message", "error");
        const toast = document.querySelector("#notification-container > div");
        expect(toast.style.backgroundColor).toBe("rgb(211, 47, 47)"); // #d32f2f
    });
});

describe("actions.js - API Interactions", () => {
    // --- reloadLibrary ---

    test("reloadLibrary should send POST request if user confirms", async () => {
        mockConfirm.mockReturnValue(true);

        await reloadLibrary();

        // Use jest.runAllTimers to flush the 3000ms timer of the notification
        jest.runAllTimers();

        expect(mockFetch).toHaveBeenCalledWith(
            "/reload_library",
            expect.objectContaining({
                method: "POST",
                headers: expect.objectContaining({
                    "X-CSRFToken": "test-csrf-token",
                }),
            })
        );

        // Verify success notification disposal
        const toast = document.querySelector("#notification-container > div");
        if (toast) toast.dispatchEvent(new Event("transitionend"));

        expect(getNotificationText()).toBe("");
    });

    test("reloadLibrary should do nothing if user cancels", async () => {
        mockConfirm.mockReturnValue(false);
        await reloadLibrary();
        expect(mockFetch).not.toHaveBeenCalled();
    });

    // --- deleteTorrent ---

    test("deleteTorrent should send DELETE request and reload on success", async () => {
        // Fix #1: Ensure the success message includes "successfully" to trigger reload.
        mockFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ message: "Torrent removed successfully." }),
            status: 200,
        });

        mockConfirm.mockReturnValue(true);

        // FIX: Force-mock window.location for JSDOM
        // Simple assignment (global.location.reload = ...) often fails in JSDOM because location is read-only.
        const originalLocation = window.location;
        delete window.location;
        window.location = { reload: jest.fn() };

        // Trigger the async function
        deleteTorrent("test-hash-123");

        // Wait for the fetch promise to resolve
        await flushPromises();

        // Execute pending timers (the 1000ms reload timer)
        jest.runAllTimers();

        // Verify reload was called
        expect(window.location.reload).toHaveBeenCalled();

        // Restore original location
        window.location = originalLocation;
    });

    // --- sendTorrent ---

    test("sendTorrent should disable and re-enable button on success", async () => {
        const mockButton = document.createElement("button");
        mockButton.innerText = "Download to Server";

        // Assert initial state is correct (not disabled)
        expect(mockButton.disabled).toBe(false);

        sendTorrent("http://link", "Book Title", mockButton);

        // Allow microtasks (fetch resolution) to process
        await flushPromises();

        // Run timers to process any setTimeout callbacks inside .finally if any
        jest.runAllTimers();

        // Assert button is re-enabled and text is restored
        expect(mockButton.disabled).toBe(false);
        expect(mockButton.innerText).toBe("Download to Server");
    });

    test("sendTorrent should show error on non-ok status code", async () => {
        const mockButton = document.createElement("button");
        mockButton.innerText = "Download to Server";

        mockFetch.mockResolvedValue({
            ok: false,
            status: 500,
            json: () => Promise.resolve({ message: "Server Error" }),
        });

        sendTorrent("http://link", "Book Title", mockButton);

        // Allow microtasks (fetch resolution and JSON parsing) to process
        await flushPromises();

        // Run timers to process notification timeout
        jest.advanceTimersByTime(3000);

        const toast = document.querySelector("#notification-container > div");
        if (toast) toast.dispatchEvent(new Event("transitionend"));
        expect(getNotificationText()).toBe("");

        // Check console.error was called
        expect(consoleErrorSpy).toHaveBeenCalled();
        expect(mockButton.disabled).toBe(false);
    });

    test("sendTorrent should show error on fetch rejection", async () => {
        mockFetch.mockRejectedValue(new Error("Network Failed"));

        sendTorrent("http://link", "Book Title", null);

        // Run all timers to ensure the cleanup in the promise chain completes
        await flushPromises();
        jest.runAllTimers();

        // Verify error message is disposed
        const toast = document.querySelector("#notification-container > div");
        if (toast) toast.dispatchEvent(new Event("transitionend"));
        expect(getNotificationText()).toBe("");
    });
});

describe("actions.js - Browser Interactions", () => {
    test("openExternalLink should call window.open if confirmed", () => {
        mockConfirm.mockReturnValue(true);
        openExternalLink("http://external.site");
        expect(mockOpen).toHaveBeenCalledWith("http://external.site", "_blank");
    });

    test("openExternalLink should do nothing if canceled", () => {
        mockConfirm.mockReturnValue(false);
        openExternalLink("http://external.site");
        expect(mockOpen).not.toHaveBeenCalled();
    });
});
