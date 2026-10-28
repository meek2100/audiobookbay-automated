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
window.showModal = showModal;
window.initSplashScreen = initSplashScreen;
window.dismissSplash = dismissSplash;
window.initMobileMenu = initMobileMenu;

function initMobileMenu() {
    const mobileMenuBtn = document.getElementById("mobile-menu-btn");
    const navLinks = document.getElementById("nav-links");
    const navBackdrop = document.getElementById("nav-backdrop");

    if (mobileMenuBtn && navLinks) {
        const toggleMobileMenu = function (forceState) {
            const isOpen = typeof forceState === "boolean" ? forceState : !navLinks.classList.contains("active");
            navLinks.classList.toggle("active", isOpen);
            mobileMenuBtn.classList.toggle("active", isOpen);
            mobileMenuBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
            if (navBackdrop) {
                navBackdrop.classList.toggle("active", isOpen);
            }
            document.body.classList.toggle("nav-open", isOpen);
        };

        mobileMenuBtn.addEventListener("click", function () {
            toggleMobileMenu();
        });

        if (navBackdrop) {
            navBackdrop.addEventListener("click", function () {
                toggleMobileMenu(false);
            });
        }

        // Close on Escape key
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && navLinks.classList.contains("active")) {
                toggleMobileMenu(false);
            }
        });

        // UX: Auto-close menu when a link is clicked
        navLinks.addEventListener("click", function (event) {
            if (event.target.closest("a")) {
                toggleMobileMenu(false);
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", function () {
    initSplashScreen();
    initMobileMenu();

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
        const sendBtn = target.closest(".send-torrent-btn");
        if (sendBtn) {
            const link = sendBtn.dataset.link;
            const title =
                sendBtn.dataset.title ||
                sendBtn.getAttribute("aria-label") ||
                document.querySelector("h1")?.textContent?.trim() ||
                "Audiobook";
            if (link) {
                sendTorrent(link, title, sendBtn);
            }
        }

        // Remove Torrent
        const removeBtn = target.closest(".remove-torrent-btn");
        if (removeBtn) {
            const id = removeBtn.dataset.torrentId;
            if (id) {
                deleteTorrent(id, removeBtn);
            }
        }

        // Download (Details Page)
        const detailsBtn = target.closest(".details-download-btn");
        if (detailsBtn) {
            const link = detailsBtn.dataset.link;
            const title = detailsBtn.dataset.title;
            if (link && title) {
                sendTorrent(link, title, detailsBtn);
            }
        }

        // External Link
        const externalBtn = target.closest(".direct-link-btn");
        if (externalBtn) {
            const link = externalBtn.dataset.externalLink;
            if (link) {
                openExternalLink(link);
            }
        }

        // Back Button
        const backBtn = target.closest(".back-link-btn");
        if (backBtn) {
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

    // If "no-splash" is present on HTML (handled by inline script),
    // we ensure overlay is hidden and return.
    if (document.documentElement.classList.contains("no-splash")) {
        splashOverlay.classList.add("hidden");
        splashOverlay.style.display = "none";
        return;
    }

    // Also double-check sessionStorage here (redundant but safe)
    if (sessionStorage.getItem("splashShown")) {
        splashOverlay.classList.add("hidden");
        splashOverlay.style.display = "none";
        return;
    }

    // Click to dismiss immediately on overlay or skip button
    splashOverlay.addEventListener("click", () => {
        if (splashVideo) {
            splashVideo.pause();
        }
        dismissSplash(splashOverlay, { skipAnimation: true });
    });

    const skipBtn = document.getElementById("skip-splash-btn");
    if (skipBtn) {
        skipBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (splashVideo) {
                splashVideo.pause();
            }
            dismissSplash(splashOverlay, { skipAnimation: true });
        });
    }

    const splashVideo = document.getElementById("splash-video");
    if (splashVideo) {
        // Video splash: Start smooth fade-out exactly 0.5s before video ends (at 3.5s for a 4s video)
        let fadingStarted = false;
        const triggerFade = () => {
            if (!fadingStarted) {
                fadingStarted = true;
                dismissSplash(splashOverlay);
            }
        };

        splashVideo.addEventListener("timeupdate", () => {
            if (splashVideo.currentTime >= 3.5) {
                triggerFade();
            }
        });

        splashVideo.addEventListener("ended", () => {
            triggerFade();
        });

        // Safety fallback timer if video fails to play or load
        setTimeout(() => {
            triggerFade();
        }, 5000);
    } else {
        // Text splash: Fade out after configured duration
        const duration = parseInt(splashOverlay.dataset.splashDuration) || 3500;
        setTimeout(() => {
            dismissSplash(splashOverlay);
        }, duration);
    }
}

function dismissSplash(overlay, options = {}) {
    if (overlay.classList.contains("hidden")) return;

    const skipAnimation = options.skipAnimation || false;
    const splashVideo = document.getElementById("splash-video");
    const targetLogo =
        document.querySelector(".masthead-logo-img") ||
        document.querySelector(".nav-logo-img") ||
        document.querySelector(".nav-logo");

    const prefersReducedMotion =
        typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Check if FLIP morph animation should be played
    let shouldMorph = false;
    let translateX = 0;
    let translateY = 0;
    let scaleX = 1;
    let scaleY = 1;
    let targetRadius = "16px";

    if (!skipAnimation && !prefersReducedMotion && splashVideo && targetLogo) {
        const targetRect = targetLogo.getBoundingClientRect();
        const videoRect = splashVideo.getBoundingClientRect();

        // Ensure valid visible bounding rectangles
        if (targetRect.width > 0 && targetRect.height > 0 && videoRect.width > 0 && videoRect.height > 0) {
            shouldMorph = true;

            const targetCenterX = targetRect.left + targetRect.width / 2;
            const targetCenterY = targetRect.top + targetRect.height / 2;
            const videoCenterX = videoRect.left + videoRect.width / 2;
            const videoCenterY = videoRect.top + videoRect.height / 2;

            translateX = targetCenterX - videoCenterX;
            translateY = targetCenterY - videoCenterY;

            scaleX = targetRect.width / videoRect.width;
            scaleY = targetRect.height / videoRect.height;

            targetRadius = window.getComputedStyle(targetLogo).borderRadius || "16px";
        }
    }

    if (shouldMorph) {
        overlay.classList.add("morphing");
        splashVideo.style.borderRadius = targetRadius;
        splashVideo.style.transform = `translate3d(${translateX}px, ${translateY}px, 0) scale(${scaleX}, ${scaleY})`;
        splashVideo.style.opacity = "0";

        // Cross-fade the target logo in as the morph reaches exact target size and position
        setTimeout(() => {
            document.documentElement.classList.add("splash-reveal-logo");
        }, 150);

        // Stagger the fade-in of the remaining page elements slightly behind the logo
        setTimeout(() => {
            document.documentElement.classList.add("splash-reveal-content");
        }, 350);

        setTimeout(() => {
            overlay.classList.add("hidden");
            overlay.style.display = "none";
            sessionStorage.setItem("splashShown", "true");
            document.documentElement.classList.add("no-splash");
            document.documentElement.classList.remove("splash-reveal-logo", "splash-reveal-content");
        }, 650);
    } else {
        overlay.classList.add("hidden");
        sessionStorage.setItem("splashShown", "true");
        document.documentElement.classList.add("no-splash");

        setTimeout(() => {
            overlay.style.display = "none";
        }, 400);
    }
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
    toast.className = "toast";
    toast.classList.add(`toast-${type}`);
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
 * Shows a custom modal confirmation dialog.
 * @param {string} title - The title of the modal.
 * @param {string} message - The message body.
 * @param {Function} onConfirm - Callback function if user confirms.
 * @param {string} confirmText - Text for the confirm button.
 * @param {string} type - 'primary' or 'danger' for button styling.
 */
function showModal(title, message, onConfirm, confirmText = "Confirm", type = "primary") {
    const modal = document.getElementById("confirmation-modal");
    if (!modal) {
        console.error("Modal element not found!");
        // Fallback to native confirm if modal is missing (safety)
        if (confirm(message)) {
            onConfirm();
        }
        return;
    }

    const titleEl = document.getElementById("modal-title");
    const bodyEl = document.getElementById("modal-body");
    const confirmBtn = document.getElementById("modal-confirm");
    const cancelBtn = document.getElementById("modal-cancel");

    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.textContent = message;

    if (confirmBtn) {
        confirmBtn.textContent = confirmText;
        // Reset classes
        confirmBtn.className = "";
        if (type === "danger") {
            confirmBtn.classList.add("btn-danger");
        } else {
            confirmBtn.classList.add("btn-primary");
        }

        // Remove old event listeners by cloning
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

        newConfirmBtn.addEventListener("click", () => {
            closeModal();
            onConfirm();
        });

        // Focus for accessibility
        setTimeout(() => newConfirmBtn.focus(), 100);
    }

    if (cancelBtn) {
        // Remove old event listeners
        const newCancelBtn = cancelBtn.cloneNode(true);
        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);

        newCancelBtn.addEventListener("click", closeModal);
    }

    // Close on overlay click
    modal.onclick = (e) => {
        if (e.target === modal) closeModal();
    };

    // Close on Escape key
    const escHandler = (e) => {
        if (e.key === "Escape") {
            closeModal();
            document.removeEventListener("keydown", escHandler);
        }
    };
    document.addEventListener("keydown", escHandler);

    // Show modal
    modal.classList.add("active");
    modal.setAttribute("aria-hidden", "false");
}

function closeModal() {
    const modal = document.getElementById("confirmation-modal");
    if (modal) {
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
    }
}

/**
 * Triggers an Audiobookshelf library scan.
 */
function reloadLibrary() {
    showModal(
        "Reload Library",
        "Are you sure you want to initiate a library scan?",
        () => {
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
                    showNotification("Could not refresh your library. Please try again in a moment.", "error");
                });
        },
        "Scan Now"
    );
}

/**
 * Deletes a torrent from the client (soft delete).
 * @param {string} torrentId - The ID or Hash of the torrent.
 * @param {HTMLElement} [buttonElement] - The button that triggered the action (optional).
 */
function deleteTorrent(torrentId, buttonElement) {
    showModal(
        "Delete Torrent",
        "Are you sure you want to remove this torrent? The downloaded files will NOT be deleted.",
        () => {
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
                    showNotification("Could not remove this download. Please try again in a moment.", "error");
                });
        },
        "Remove",
        "danger"
    );
}

/**
 * Sends a magnet link to the configured torrent client.
 * @param {string} link - The URL/Magnet link.
 * @param {string} title - The book title.
 * @param {HTMLElement} buttonElement - The button clicked (for state management).
 */
function sendTorrent(link, title, buttonElement) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

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

                // Add timeout to reset button
                setTimeout(() => {
                    buttonElement.disabled = false;
                    buttonElement.innerHTML = originalBtnHTML;
                }, 3000);
            }
        })
        .catch((error) => {
            console.error("Download failed:", error);
            showNotification(
                "Could not start download. Please check that your download app is running and try again.",
                "error"
            );
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
        "You are about to open this link directly in your browser.\n" +
        "This traffic will NOT be routed through the server's connection.\n\n" +
        "Your IP address and traffic may be exposed.";

    showModal(
        "External Link Warning",
        warningMessage,
        () => {
            window.open(url, "_blank");
        },
        "Proceed",
        "primary"
    );
}
