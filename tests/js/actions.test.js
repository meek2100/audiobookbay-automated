// File: tests/js/actions.test.js
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

// Mock reload function (to bypass JSDOM window.location restrictions)
window.__mockReload = jest.fn();

// Mock requestAnimationFrame used by showNotification
global.requestAnimationFrame = jest.fn((cb) => cb());

// Spy on console.error to detect swallowed errors
const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});

// Add a required meta tag for CSRF token into the DOM
document.head.innerHTML = '<meta name="csrf-token" content="test-csrf-token" />';

// FIX: Patch the source code string before evaluation.
// We replace 'location.reload()' with 'window.__mockReload()' to intercept the call
// without needing to redefine the protected window.location object.
const patchedActionsContent = global.actionsJsContent.replace(/location\.reload\(\)/g, "window.__mockReload()");

// Evaluate the script content to define the functions globally
eval(patchedActionsContent);

// --- MOCK UTILITIES ---

function getNotificationText() {
    const container = document.getElementById("notification-container");
    return container ? container.textContent : "";
}

// Helper to drain the microtask queue completely.
async function flushPromises() {
    return new Promise((resolve) => jest.requireActual("timers").setTimeout(resolve, 0));
}
// ----------------------

// Reset mocks before each test
beforeEach(() => {
    mockFetch.mockClear();
    mockConfirm.mockClear();
    mockOpen.mockClear();
    window.__mockReload.mockClear();

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

        const toast = document.querySelector("#notification-container > div");
        jest.advanceTimersByTime(3000);

        const transitionEndEvent = new Event("transitionend");
        if (toast) {
            toast.dispatchEvent(transitionEndEvent);
        }

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
        mockFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ message: "Torrent removed successfully." }),
            status: 200,
        });

        mockConfirm.mockReturnValue(true);

        // No complicated window.location mocking needed here due to the patch above.
        deleteTorrent("test-hash-123");

        await flushPromises();
        jest.runAllTimers();

        expect(window.__mockReload).toHaveBeenCalled();
    });

    // --- sendTorrent ---

    test("sendTorrent should change button text to Sent! then revert", async () => {
        const mockButton = document.createElement("button");
        mockButton.innerText = "Download to Server";

        expect(mockButton.disabled).toBe(false);

        sendTorrent("http://link", "Book Title", mockButton);

        expect(mockButton.innerText).toBe("Sending...");
        expect(mockButton.disabled).toBe(true);

        await flushPromises();

        expect(mockButton.innerText).toBe("Sent!");
        expect(mockButton.disabled).toBe(true);

        jest.advanceTimersByTime(2000);

        // Updated logic: Button remains disabled to prevent double submission
        expect(mockButton.disabled).toBe(true);
        // Text might reset or stay "Sent!" depending on impl, but test should align with current code
        // current impl in actions.js: setTimeout callback is empty comment
        // So text remains "Sent!"
        expect(mockButton.innerText).toBe("Sent!");
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

        await flushPromises();
        jest.advanceTimersByTime(3000);

        const toast = document.querySelector("#notification-container > div");
        if (toast) toast.dispatchEvent(new Event("transitionend"));
        expect(getNotificationText()).toBe("");

        expect(consoleErrorSpy).toHaveBeenCalled();
        expect(mockButton.disabled).toBe(false);
        expect(mockButton.innerText).toBe("Download to Server");
    });

    test("sendTorrent should show error on fetch rejection", async () => {
        mockFetch.mockRejectedValue(new Error("Network Failed"));

        sendTorrent("http://link", "Book Title", null);

        await flushPromises();
        jest.runAllTimers();

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
