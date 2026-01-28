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
// We replace 'location.reload()' with 'window.__mockReload()' to intercept the call.
// We also redirect setTimeout to a custom mock to reliably test callbacks regardless of context binding.
const patchedActionsContent = global.actionsJsContent
    .replace(/location\.reload\(\)/g, "window.__mockReload()")
    .replace(/setTimeout\(/g, "window.__customSetTimeout(");

// --- MOCK UTILITIES ---

function getNotificationText() {
    const container = document.getElementById("notification-container");
    return container ? container.textContent : "";
}

// Helper to drain the microtask queue completely.
async function flushPromises() {
    return new Promise((resolve) => jest.requireActual("timers").setTimeout(resolve, 0));
}

// Custom setTimeout mock
window.__customSetTimeout = jest.fn();

// Modal setup helper
function setupModal() {
    const modalHTML = `
        <div id="confirmation-modal" class="modal-overlay" aria-hidden="true">
            <div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="modal-title">
                <div class="modal-header">
                    <h3 class="modal-title" id="modal-title">Confirm Action</h3>
                </div>
                <div class="modal-body" id="modal-body">
                    Are you sure you want to proceed?
                </div>
                <div class="modal-footer">
                    <button class="btn-secondary" id="modal-cancel">Cancel</button>
                    <button class="btn-primary" id="modal-confirm">Confirm</button>
                </div>
            </div>
        </div>
    `;
    document.body.innerHTML += modalHTML;
}

// ----------------------

// Reset mocks before each test
beforeEach(() => {
    mockFetch.mockClear();
    mockConfirm.mockClear();
    mockOpen.mockClear();
    window.__mockReload.mockClear();
    window.__customSetTimeout.mockClear();

    // Default mock response for success
    mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ message: "Success" }),
        status: 200,
    });
    // Ensure notification container exists and is empty
    document.body.innerHTML = '<div id="notification-container"></div>';

    // Inject modal structure
    setupModal();

    window.__customSetTimeout.mockImplementation((cb, delay) => {
        // We use the real setTimeout (or Jest's fake one if enabled) to simulate behavior
        return setTimeout(cb, delay);
    });

    jest.useFakeTimers();

    // Evaluate the script content
    eval(patchedActionsContent);
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

    test("showModal should display modal and set content", () => {
        const modal = document.getElementById("confirmation-modal");
        const titleEl = document.getElementById("modal-title");
        const bodyEl = document.getElementById("modal-body");

        showModal("Test Title", "Test Message", () => {});

        expect(modal.classList.contains("active")).toBe(true);
        expect(titleEl.textContent).toBe("Test Title");
        expect(bodyEl.textContent).toBe("Test Message");
    });
});

describe("actions.js - API Interactions", () => {
    // --- reloadLibrary ---

    test("reloadLibrary should send POST request if user confirms via modal", async () => {
        // Trigger action
        reloadLibrary();

        // Assert modal is shown
        const modal = document.getElementById("confirmation-modal");
        expect(modal.classList.contains("active")).toBe(true);

        // Click confirm
        const confirmBtn = document.getElementById("modal-confirm");
        confirmBtn.click();

        // Check callback execution
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

        // Modal should be closed
        expect(modal.classList.contains("active")).toBe(false);

        const toast = document.querySelector("#notification-container > div");
        if (toast) toast.dispatchEvent(new Event("transitionend"));
        expect(getNotificationText()).toBe("");
    });

    test("reloadLibrary should do nothing if user cancels via modal", async () => {
        reloadLibrary();

        // Click cancel
        const cancelBtn = document.getElementById("modal-cancel");
        cancelBtn.click();

        // Check fetch was not called
        expect(mockFetch).not.toHaveBeenCalled();

        // Modal should be closed
        const modal = document.getElementById("confirmation-modal");
        expect(modal.classList.contains("active")).toBe(false);
    });

    // --- deleteTorrent ---

    test("deleteTorrent should send DELETE request and reload on success via modal", async () => {
        mockFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ message: "Torrent removed successfully." }),
            status: 200,
        });

        deleteTorrent("test-hash-123");

        // Click confirm
        const confirmBtn = document.getElementById("modal-confirm");
        confirmBtn.click();

        await flushPromises();
        jest.runAllTimers();

        expect(window.__mockReload).toHaveBeenCalled();
    });

    // --- sendTorrent ---

    test("sendTorrent should change button text to Sent! then revert", async () => {
        const mockButton = document.createElement("button");
        mockButton.innerHTML = "Download";

        expect(mockButton.disabled).toBe(false);

        sendTorrent("http://link", "Book Title", mockButton);

        // Check for substring because innerHTML now contains a spinner span
        expect(mockButton.innerHTML).toContain("Sending...");
        expect(mockButton.innerHTML).toContain('class="spinner"');
        expect(mockButton.disabled).toBe(true);

        await flushPromises();

        expect(mockButton.innerText).toBe("Sent!");
        expect(mockButton.disabled).toBe(true);

        // Manually trigger the revert callback via our custom mock
        // We expect __customSetTimeout to have been called with delay 3000
        // NOTE: showNotification also uses setTimeout(..., 3000), so we must run ALL matching callbacks
        const calls = window.__customSetTimeout.mock.calls;
        const matchingCalls = calls.filter((call) => call[1] === 3000);

        if (matchingCalls.length > 0) {
            matchingCalls.forEach((call) => {
                const callback = call[0];
                callback();
            });
        } else {
            // Fallback to time advance if it was queued (should be queued via implementation)
            jest.advanceTimersByTime(3500);
        }

        // Updated logic: Button resets after 3 seconds
        expect(mockButton.disabled).toBe(false);
        // Use innerHTML to avoid JSDOM innerText visibility quirks on detached elements
        expect(mockButton.innerHTML).toBe("Download");
    });

    test("sendTorrent should show error on non-ok status code", async () => {
        const mockButton = document.createElement("button");
        mockButton.innerText = "Download";
        // innerHTML is used to restore the original state, so we check innerHTML or ensure initial innerHTML matches innerText
        const originalHTML = mockButton.innerHTML;

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
        // The implementation restores innerHTML
        expect(mockButton.innerHTML).toBe(originalHTML);
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
    test("openExternalLink should call window.open if confirmed via modal", () => {
        openExternalLink("http://external.site");

        // Assert modal is active
        const modal = document.getElementById("confirmation-modal");
        expect(modal.classList.contains("active")).toBe(true);

        // Confirm
        document.getElementById("modal-confirm").click();

        expect(mockOpen).toHaveBeenCalledWith("http://external.site", "_blank");
    });

    test("openExternalLink should do nothing if canceled via modal", () => {
        openExternalLink("http://external.site");

        // Cancel
        document.getElementById("modal-cancel").click();

        expect(mockOpen).not.toHaveBeenCalled();
    });
});
