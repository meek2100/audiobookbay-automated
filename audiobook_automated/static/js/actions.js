// File: audiobook_automated/static/js/actions.js
/**
 * Global application actions (Reload ABS, Delete Torrent, Send Torrent, Open External)
 */

// Explicitly expose functions to the global scope (window) for testability and consistency.
window.showNotification = showNotification;
window.reloadLibrary = reloadLibrary;
window.deleteTorrent = deleteTorrent;
window.sendTorrent = sendTorrent;
window.openExternalLink = openExternalLink;

document.addEventListener("DOMContentLoaded", function () {
    initSplashScreen();

    // Mobile Menu Toggle Logic
    const mobileMenuBtn = document.getElementById("mobile-menu-btn");
    const navLinks = document.getElementById("nav-links");

    if (mobileMenuBtn && navLinks) {
        mobileMenuBtn.addEventListener("click", function () {
            navLinks.classList.toggle("active");
        });

        // UX: Auto-close menu when a link is clicked
        navLinks.addEventListener("click", function (event) {
            if (event.target.tagName === "A") {
                navLinks.classList.remove("active");
            }
        });
    }

    // Reload Library Button
    const reloadBtn = document.getElementById("reload-library-btn");
    if (reloadBtn) {
        reloadBtn.addEventListener("click", function (e) {
            e.preventDefault();
            reloadLibrary();
        });
    }

    // Global Error Handler for Images (Capture Phase)
    window.addEventListener(
        "error",
        function (event) {
            if (event.target && event.target.tagName === "IMG") {
                const img = event.target;
                const defaultCover = img.getAttribute("data-default-cover");
                if (defaultCover && img.src !== defaultCover) {
                    // Prevent infinite loops if default cover is also broken
                    img.src = defaultCover;
                }
            }
        },
        true // Capture phase to catch error events which don't bubble
    );

    // Event Delegation for Buttons
    document.body.addEventListener("click", function (event) {
        const target = event.target;

        // Send Torrent
        if (target.matches(".send-torrent-btn")) {
            const link = target.dataset.link;
            const title = target.dataset.title;
            if (link && title) {
                sendTorrent(link, title, target);
            }
        }

        // Remove Torrent
        if (target.matches(".remove-torrent-btn")) {
            const id = target.dataset.torrentId;
            if (id) {
                deleteTorrent(id, target);
            }
        }

        // Download (Details Page)
        if (target.matches(".details-download-btn")) {
            const link = target.dataset.link;
            const title = target.dataset.title;
            if (link && title) {
                sendTorrent(link, title, target);
            }
        }

        // External Link
        if (target.matches(".direct-link-btn")) {
            const link = target.dataset.externalLink;
            if (link) {
                openExternalLink(link);
            }
        }

        // Back Button
        if (target.matches(".back-link-btn")) {
            history.back();
        }
    });
});

/**
 * Initializes the splash screen logic.
 * Shows only on first visit (sessionStorage).
 */
function initSplashScreen() {
    const splashOverlay = document.getElementById("splash-overlay");
    if (!splashOverlay) return;

    // Check if already shown in this session
    if (sessionStorage.getItem("splashShown")) {
        splashOverlay.style.display = "none";
        return;
    }

    // Show splash
    splashOverlay.classList.add("active");

    // Click to dismiss immediately
    splashOverlay.addEventListener("click", () => {
        splashOverlay.classList.remove("active");
        setTimeout(() => {
            splashOverlay.style.display = "none";
            sessionStorage.setItem("splashShown", "true");
        }, 300); // Faster fade out on click
    });

    // Read duration from data attribute
    const duration = parseInt(splashOverlay.dataset.splashDuration) || 4500;

    // Fade out after delay
    setTimeout(() => {
        // Only run if still active (not clicked yet)
        if (splashOverlay.classList.contains("active")) {
            splashOverlay.classList.remove("active");

            // Wait for CSS transition to finish before hiding/removing
            setTimeout(() => {
                splashOverlay.style.display = "none";
                sessionStorage.setItem("splashShown", "true");
            }, 1500); // Matches CSS opacity transition time
        }
    }, duration);
}

/**
 * Displays a toast notification.
 * @param {string} message - The message to display.
 * @param {string} type - 'info' (green) or 'error' (red).
 */
function showNotification(message, type = "info") {
    // Create a notification container if it doesn't exist
    let container = document.getElementById("notification-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "notification-container";
        document.body.appendChild(container);
    }

    // Apply styles to ensure it floats correctly (fixes issue if element exists in HTML but isn't styled)
    container.style.position = "fixed";
    container.style.top = "20px";
    container.style.left = "50%";
    container.style.transform = "translateX(-50%)";
    container.style.zIndex = "10000";
    container.style.display = "flex";
    container.style.flexDirection = "column";
    container.style.gap = "10px";

    const toast = document.createElement("div");
    toast.style.padding = "12px 24px";
    toast.style.borderRadius = "5px";
    toast.style.color = "#fff";
    toast.style.fontSize = "1rem";
    toast.style.boxShadow = "0 4px 6px rgba(0,0,0,0.2)";
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";

    // Color based on type
    if (type === "error") {
        toast.style.backgroundColor = "#d32f2f"; // Red
    } else {
        toast.style.backgroundColor = "#43a047"; // Green
    }

    toast.textContent = message;
    container.appendChild(toast);

    // Fade in
    requestAnimationFrame(() => {
        toast.style.opacity = "1";
    });

    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.addEventListener("transitionend", () => {
            toast.remove();
        });
    }, 3000);
}

/**
 * Triggers an Audiobookshelf library scan.
 */
function reloadLibrary() {
    if (!confirm("Are you sure you want to initiate a library scan?")) {
        return;
    }

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

    fetch("/reload_library", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
        },
    })
        .then((response) => response.json())
        .then((data) => {
            if (data.message.toLowerCase().includes("failed")) {
                showNotification(data.message, "error");
            } else {
                showNotification(data.message, "success");
            }
        })
        .catch((error) => {
            console.error("Error:", error);
            showNotification("An error occurred while trying to reload the library.", "error");
        })
        .finally(() => {
            // No specific UI state to reset here, but keeping consistent pattern
        });
}

/**
 * Deletes a torrent from the client (soft delete).
 * @param {string} torrentId - The ID or Hash of the torrent.
 * @param {HTMLElement} [buttonElement] - The button that triggered the action (optional).
 */
function deleteTorrent(torrentId, buttonElement) {
    if (!confirm("Are you sure you want to remove this torrent? The downloaded files will NOT be deleted.")) {
        return;
    }

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

    fetch("/delete", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ id: torrentId }),
    })
        .then((response) => response.json())
        .then((data) => {
            showNotification(data.message, "success");
            if (data.message.includes("successfully")) {
                // Remove the row from the DOM if buttonElement is provided
                if (buttonElement) {
                    const row = buttonElement.closest("tr");
                    if (row) {
                        row.remove();
                    } else {
                        // Fallback if no row found (unlikely in status table)
                        setTimeout(() => location.reload(), 1000);
                    }
                } else {
                    setTimeout(() => location.reload(), 1000);
                }
            }
        })
        .catch((error) => {
            console.error("Error:", error);
            showNotification("An error occurred while removing the torrent.", "error");
        })
        .finally(() => {
            // Reset UI state if needed (currently delete removes row or reloads)
        });
}

/**
 * Sends a magnet link to the configured torrent client.
 * @param {string} link - The URL/Magnet link.
 * @param {string} title - The book title.
 * @param {HTMLElement} buttonElement - The button clicked (for state management).
 */
function sendTorrent(link, title, buttonElement) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (!csrfMeta) {
        showNotification("Security Error: CSRF token missing. Please refresh the page.", "error");
        return;
    }
    const csrfToken = csrfMeta.getAttribute("content");

    // Disable specific button to prevent double-clicks
    let originalBtnHTML = "";
    if (buttonElement) {
        buttonElement.disabled = true;
        originalBtnHTML = buttonElement.innerHTML;
        // Use innerHTML to include the spinner div
        buttonElement.innerHTML = '<span class="spinner"></span> Sending...';
    }

    fetch("/send", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ link: link, title: title }),
    })
        .then((response) => {
            if (!response.ok) {
                return response
                    .json()
                    .then((err) => {
                        throw new Error(err.message || "Server Error");
                    })
                    .catch(() => {
                        throw new Error(`Request failed with status ${response.status}`);
                    });
            }
            return response.json();
        })
        .then((data) => {
            showNotification(data.message, "success");
            // Improve UX: Show "Sent!" state temporarily
            if (buttonElement) {
                buttonElement.innerText = "Sent!";
                // Keep disabled to prevent re-submission
                buttonElement.disabled = true;
            }
        })
        .catch((error) => {
            console.error("Download failed:", error);
            showNotification("Failed to send download: " + error.message, "error");
            // Allow retry on error
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = originalBtnHTML;
            }
        })
        .finally(() => {
            // Ensure any necessary cleanup happens here
        });
}

/**
 * Opens a link in a new tab with a security confirmation.
 * @param {string} url - The URL to open.
 */
function openExternalLink(url) {
    const warningMessage =
        "SECURITY WARNING:\n\n" +
        "You are about to open this link directly in your browser.\n" +
        "This traffic will NOT be routed through the server's connection.\n\n" +
        "Your IP address and traffic may be exposed.\n\n" +
        "Are you sure you want to proceed?";

    if (confirm(warningMessage)) {
        window.open(url, "_blank");
    }
}
